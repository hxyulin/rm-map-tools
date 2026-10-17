#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Fit Energy Unit exterior profiles at explicit angular/axial LOD controls."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_radial_profile import radial_samples, select_profile_rows, profile_mesh, clip_below
from mesh_quality import deviation
from plan_cad_lods import digest
from gltf_scene import read_glb, write_glb


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    cid = 'energy-unit/unit'; composed = ROOT / 'out/rmuc2027-composed-pipeline' / cid
    record = json.loads((composed / 'summary.json').read_bytes()); path = composed / 'candidate.npz'
    if digest(composed / 'candidate.glb') != record['candidate_sha256']: raise ValueError('composed reference changed')
    # Profile discovery samples original .4/.6 source, not the previous LOD.
    original = ROOT / 'out/rmuc2027-mounting-native' / cid / 'combined.npz'
    source_report = json.loads(original.with_name('summary.json').read_bytes())
    if digest(original) != source_report['stages']['combined']['outputs_sha256']['combined.npz']: raise ValueError('edited native source changed')
    raw = dict(np.load(original)); owners = np.load(original.with_name('combined-native-face-indices.npy'))
    # Energy exterior is qualified shell 1; native faces 1..1218, shell 2 is the enclosed cavity.
    # Resolve that domain from the actual original native import, not an unqualified ordinal cutoff.
    spec = importlib.util.spec_from_file_location('composition', ROOT / 'benchmarks/2026-10-17-composed-pipeline/run.py')
    composition = importlib.util.module_from_spec(spec); spec.loader.exec_module(composition)
    doc, reader, faces, shells, face_owner = composition.native(ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step')
    selected = np.array([face_owner[abs(int(i))] == 1 for i in owners])
    p = raw['positions_mm']; t = raw['triangles'][selected]; m = raw['material_ids'][selected]
    palette = [v or None for v in raw['palette'].tolist()]
    # Source-bound central cylindrical axis is local +Y through X=Z=0.
    records = json.loads((ROOT / 'out/rmuc2027-equipment-opportunities' / cid / 'audit.json').read_bytes())
    support = next(s for s in records['top_cylinder_support_candidates'] if abs(s['radius_mm'] - 29.9) < 1e-5)
    if not np.allclose(support['axis_direction'], [0, 1, 0], atol=1e-8) or np.linalg.norm(support['axis_anchor_mm']) > 1e-5:
        raise ValueError('Energy axis binding changed')
    low, high = p[t, 1].min(), p[t, 1].max()
    profile_low = 25.0  # Native housing/body interface, keeping the entire lower housing.
    heights = np.linspace(profile_low + 1e-5, high - 1e-5, 501)
    pipe = composition.module('pipeline', ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py')
    reference = dict(np.load(path))
    original_g = reference['positions_mm'][reference['triangles']]
    lower_p, lower_t, lower_m, lower_owners = clip_below(reference['positions_mm'], reference['triangles'], reference['material_ids'], axis=1, height_mm=profile_low)
    # The open lower socket continues behind the outer body. Radial first-hit
    # profiles cannot represent it: retain its small-radius walls and axial
    # surfaces as source geometry, including the deep stop plate.
    radius_at_vertices = np.linalg.norm(original_g[:, :, [0, 2]], axis=2)
    top_mask = (original_g[:, :, 1].min(1) >= profile_low - 1e-4) & ((radius_at_vertices.max(1) <= 28.5) | (np.ptp(original_g[:, :, 1], axis=1) < 1e-4))
    top_mask &= ~np.all(abs(original_g[:, :, 1] - profile_low) < 1e-4, axis=1)
    reference_palette = [v or None for v in reference['palette'].tolist()]
    material_remap = np.array([palette.index(c) for c in reference_palette])
    retained_p = np.concatenate([lower_p, reference['positions_mm']])
    retained_t = np.concatenate([lower_t, reference['triangles'][top_mask] + len(lower_p)])
    retained_m = material_remap[np.r_[lower_m, reference['material_ids'][top_mask]]]
    candidates = []
    for segments in [48, 96]:
        angles = np.arange(segments) * 2 * math.pi / segments
        radii, colors = radial_samples(p, t, m, heights_mm=heights, angles_rad=angles)
        selected_rows = select_profile_rows(heights, radii, colors, tolerance_mm=.2)
        knots = heights[selected_rows].copy(); knots[[0, -1]] = [profile_low, high]
        # Read source colors at actual output side-quad centers, preserving the source palette.
        mids = (knots[:-1] + knots[1:]) / 2
        _, side_colors = radial_samples(p, t, m, heights_mm=mids, angles_rad=angles + math.pi / segments)
        # Authored end surfaces are grey; verify their source native endpoint triangles.
        caps = []
        for y in [low, high]:
            cap = np.all(abs(p[t, 1] - y) < 1e-4, axis=1)
            keys, counts = np.unique(m[cap], return_counts=True)
            if len(keys) != 1: raise ValueError('end-cap source paint is not uniform')
            caps.append(int(keys[0]))
        q, f, k = profile_mesh(knots, angles, radii[selected_rows], side_colors, cap_material_ids=caps)
        # Discard generic cap fans; keep source-owned end/recess triangles exactly.
        f = f[:-2 * segments]; k = k[:-2 * segments]
        generated_count = len(f)
        f = np.concatenate([f, retained_t + len(q)])
        k = np.r_[k, retained_m]
        q = np.concatenate([q, retained_p])
        units = np.r_[np.full(generated_count, -1, int), np.full(len(retained_t), -2, int)]
        stage = 'profile-' + str(segments); pipe.save_mesh(out, stage, q, f, k, palette, units)
        export_doc, export_blob = read_glb(out / (stage + '.glb'))
        for node in export_doc['nodes']:
            if 'mesh' in node:
                node['extras'].update(derived_geometry=True, native_identity_claim=False,
                                     geometry_role='radial-side-profile' if node['extras']['native_shell_index'] == -1 else 'source-retained-or-clipped-end-regions')
        write_glb(out / (stage + '.glb'), export_doc, export_blob)
        quality = deviation(p, t, q, f, count=32768)
        reference = dict(np.load(path)); baseline = len(reference['triangles'])
        data = {'schema': 'radial-section-profile-v1', 'source_npz_sha256': digest(original),
                'axis': [0, 1, 0], 'axis_centre_mm': [0, 0, 0], 'angular_segments': segments,
                'height_knots_mm': knots.tolist(), 'radii_mm': radii[selected_rows].tolist(),
                'side_material_ids': side_colors.tolist(), 'palette': palette, 'cap_material_ids': caps, 'generated_caps_discarded': True,
                'retained_lower_source_triangle_indices': lower_owners.tolist(), 'retained_top_source_triangle_indices': np.flatnonzero(top_mask).tolist(),
                'reference_npz_sha256': digest(path),
                'sampled_axial_chord_tolerance_mm': .2, 'discovery_height_step_mm': float(heights[1] - heights[0])}
        (out / (stage + '.json')).write_text(json.dumps(data, indent=2) + '\n')
        row = {'name': stage, 'angular_segments': segments, 'axial_rings': len(knots),
               'triangles': len(f), 'retained_end_triangles': len(retained_t), 'composed_reference_triangles': baseline,
               'placed_uses': 12, 'placed_saving': (baseline - len(f)) * 12,
               'sampled_native_exterior_deviation_mm': quality,
               'outputs_sha256': {name: digest(out / name) for name in [stage + '.glb', stage + '.npz', stage + '.json']}}
        candidates.append(row); print(row, flush=True)
    report = {'source_step_sha256': record['source_step_sha256'], 'edited_native_sha256': digest(original),
              'composed_reference_sha256': record['candidate_sha256'], 'composed_reference_npz_sha256': digest(path),
              'source_geometry': 'Edited original source native exterior; cavity excluded by prior proof.',
              'candidates': candidates, 'producer_sha256': {str(v.relative_to(ROOT)): digest(v) for v in [Path(__file__), ROOT / 'python/cad_radial_profile.py']},
              'scope': 'Approximate radial first-hit side exterior with shared axial knots, source color samples and explicit angular LOD. Source lower housing/recess retained by triangle-plane clipping at 25 mm; small-radius socket walls and axial end faces copied exactly; generated cap fans discarded. Radially hidden surfaces omitted; undercuts and small details can change. Not source-solid, collision, detector or runtime replacement. Visual review required.'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')

if __name__ == '__main__': main()
