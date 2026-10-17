#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Revolve a complete native Energy meridian, including socket and undercuts."""
import argparse
import json
import math
from pathlib import Path
from audit import ROOT, native, module
import numpy as np
from cad_collision_profiles import meridian_section, revolve_profile
from mesh_quality import deviation, distances
from plan_cad_lods import digest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from gltf_scene import read_glb, write_glb

save_mesh = module('equipment', ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py').save_mesh


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    cid = 'energy-unit/unit'; source = ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step'; baseline = ROOT / 'out/rmuc2027-composed-pipeline' / cid / 'candidate.npz'
    inventory = json.loads(source.with_name('native.json').read_bytes())
    if digest(source) != inventory['source_step_sha256']: raise ValueError('native Energy source changed')
    doc, reader, faces, shells, owners = native(source); solid = BRepBuilderAPI_MakeSolid(TopoDS.Shell(shells.FindKey(1))).Solid()
    support = BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(609))).Cylinder()
    if owners[609] != 1 or abs(support.Radius() - 20) > 1e-6 or not np.allclose(np.abs(support.Axis().Direction().Coord()), [0, 1, 0], atol=1e-8) or np.linalg.norm(np.array(support.Location().Coord())[[0, 2]]) > 1e-6: raise ValueError('native Energy socket axis binding changed')
    original = np.load(ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'native.npz'); p, t, units = [original[k] for k in ['positions_mm', 'triangles', 'unit_ids']]; t = t[units == 1]
    reference = np.load(baseline); folder = out / cid; folder.mkdir(parents=True, exist_ok=True); rows = []
    # Source-bound axis and exterior owner are the same qualified domain as the
    # earlier visual trials; enclosed shell 2 is not a second exterior collider.
    # A bounded three-section comparison detects azimuth-dependent collars.
    # The guard remains six millimetres; a bad meridian cannot raise it.
    trials = []
    for angle in [.077, .85, math.pi / 3]:
        loops, _ = meridian_section(solid, angle_rad=angle, radius_limit_mm=60, height_range_mm=(-1, 151), boundary_error_mm=1)
        q, f, _ = revolve_profile(loops, angular_segments=24)
        quality = deviation(p, t, q, f, count=max(len(t), len(f)))
        quality['maximum_vertex_distance_mm'] = float(max(distances(p[np.unique(t)], q, f).max(), distances(q[np.unique(f)], p, t).max()))
        trials.append({'angle_rad': angle, 'triangles': len(f), 'native_exterior_deviation_mm': quality})
    best = min(trials, key=lambda r: max(r['native_exterior_deviation_mm']['max'], r['native_exterior_deviation_mm']['maximum_vertex_distance_mm']))
    if max(best['native_exterior_deviation_mm']['max'], best['native_exterior_deviation_mm']['maximum_vertex_distance_mm']) > 6: raise ValueError('no Energy meridian meets the six millimetre guard')
    for nominal in [.5, 1.0]:
        loops, proof = meridian_section(solid, angle_rad=best['angle_rad'], radius_limit_mm=60, height_range_mm=(-1, 151), boundary_error_mm=nominal)
        for segments in [24, 32]:
            q, f, topology = revolve_profile(loops, angular_segments=segments)
            stage = f'meridian-{nominal:g}-{segments}'; save_mesh(folder, stage, q, f, np.zeros(len(f), dtype=np.int64), ['0.45,0.65,0.80'], np.full(len(f), -1, dtype=np.int64))
            path = folder / (stage + '.glb'); d, blob = read_glb(path)
            for node in d['nodes']:
                if 'mesh' in node: node['extras'].update(derived_geometry=True, native_identity_claim=False, source_native_shell_index=1, collision_only=True)
            write_glb(path, d, blob)
            raw = deviation(p, t, q, f, count=max(len(t), len(f)))
            raw['maximum_vertex_distance_mm'] = float(max(distances(p[np.unique(t)], q, f).max(), distances(q[np.unique(f)], p, t).max()))
            visual = deviation(reference['positions_mm'], reference['triangles'], q, f, count=32768)
            row = {'stage': stage, 'angular_segments': segments, 'boundary_allowance_mm': nominal, 'triangles': len(f), 'meridian_vertices': sum(len(r['points_ry_mm']) for r in loops), 'native_exterior_deviation_mm': raw, 'approved_visual_deviation_mm': visual,
                   'topology': topology, 'profile': proof, 'meridian_loops': [{'outer': r['outer'], 'points_ry_mm': r['points_ry_mm'].tolist()} for r in loops], 'outputs_sha256': {stage + ext: digest(folder / (stage + ext)) for ext in ['.glb', '.npz']}}
            rows.append(row); print(stage, len(f), raw, flush=True)
    (out / 'energy-summary.json').write_text(json.dumps({'id': cid, 'source_step_sha256': digest(source), 'axis_support_native_face': 609, 'native_npz_sha256': digest(ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'native.npz'), 'reference_npz_sha256': digest(baseline), 'reference_triangles': len(reference['triangles']), 'uses': 12, 'variants': rows, 'azimuth_trials': trials, 'selected_angle_rad': best['angle_rad'],
                                                       'producer_sha256': digest(__file__), 'pass_sha256': digest(ROOT / 'python/cad_collision_profiles.py'), 'scope': 'Collision-only complete source meridian revolved about the qualified +Y axis. Source socket/annular recess topology retained in the meridian; angular asymmetry simplified. No runtime or scoring replacement.'}, indent=2) + '\n')


if __name__ == '__main__': main()
