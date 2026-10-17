#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build shared-edge road LODs independently from visual-only collision roles.

DJI / RoboMaster owns the source geometry and appearance. Inspection candidates
only; the installed field, scoring geometry and source STEP remain unchanged.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_extrusion_skin import extrusion_skin
from mesh_parts import tessellate
from mesh_quality import deviation
from plan_cad_lods import digest
from export_field_package import GlbWriter


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


native = module('composition', ROOT / 'benchmarks/2026-10-17-composed-pipeline/run.py').native
save_mesh = module('equipment', ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py').save_mesh


def save_faces(folder, stage, p, t, m, palette, face_ids):
    """Batch the rigid terrain by material, retaining source face index runs."""
    np.savez(folder / (stage + '.npz'), positions_mm=p, triangles=t, material_ids=m,
             source_face_ids=face_ids, palette=np.array([v or '' for v in palette]))
    colors = [palette[k] for k in m]
    writer = GlbWriter(stage, {'version': '2.0', 'copyright': 'DJI / RoboMaster source geometry and appearance; inspection candidate'})
    writer.add_node('rigid-road', p / 1000, t, colors, extras={'inspection_only': True, 'derived_geometry': stage != 'reference'})
    # Primitive triangle order is the input order restricted to its material.
    # Metadata preserves face selection without making every face a draw call.
    keys = sorted(set(colors), key=lambda k: (k is None, k))
    for prim, color in zip(writer.meshes[0]['primitives'], keys):
        ids = face_ids[np.array([c == color for c in colors])]
        starts = np.r_[0, np.flatnonzero(ids[1:] != ids[:-1]) + 1]
        ends = np.r_[starts[1:], len(ids)]
        prim['extras'] = {'source_native_face_runs': [{'first_triangle': int(a), 'triangle_count': int(b - a), 'source_face_index': int(ids[a])} for a, b in zip(starts, ends)]}
    writer.write(folder / (stage + '.glb'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    audit = json.loads((ROOT / 'out/rmuc2027-terrain-cost-full/audit.json').read_bytes())
    rows = []
    for c in audit['components']:
        selected = [f['native_face_index'] for f in c['faces'] if f['surface'] == 'SurfaceOfExtrusion' and f['triangles'] > 2000]
        if not selected: continue
        cid = c['id']; folder = args.out / cid; folder.mkdir(parents=True, exist_ok=True)
        source = ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step'
        if digest(source) != c['component_step_sha256']: raise ValueError('source changed')
        doc, reader, faces, shells, owner = native(source); face_ids = []; stats = {}
        p, t, m, palette = tessellate(doc, .4, .25, stats, lambda _, face, n: face_ids.extend([faces.FindIndex(face)] * n))
        face_ids = np.array(face_ids)
        if len(t) != c['triangles'] or stats.get('unmeshed_faces'): raise ValueError('incomplete source mesh')
        save_faces(folder, 'reference', p, t, m, palette, face_ids)
        variants = []
        # Visual and collision start at the same approved profile resolution.
        # 24 is a finer visual option; 12 is a separate collision experiment.
        for per_wave, allowance in [(12, 1.2), (16, .75), (24, .35)]:
            replacements, proof = extrusion_skin(faces, selected, sections=per_wave * 10, maximum_profile_error_mm=allowance)
            chunks = []; triangles = []; materials = []; ids = []; offset = 0
            for i in range(1, faces.Extent() + 1):
                mask = face_ids == i
                keys = np.unique(m[mask])
                if i in replacements:
                    if len(keys) != 1: raise ValueError('ambiguous source face appearance')
                    q, f = replacements[i]; k = np.full(len(f), keys[0])
                else:
                    used, inv = np.unique(t[mask], return_inverse=True)
                    q, f, k = p[used], inv.reshape(-1, 3), m[mask]
                chunks.append(q); triangles.append(f + offset); materials.append(k); ids.extend([i] * len(f)); offset += len(q)
            q = np.concatenate(chunks); f = np.concatenate(triangles); k = np.concatenate(materials)
            quality = deviation(p, t, q, f, count=16384)
            if quality['max'] > allowance + .05: raise ValueError('whole-component deviation failed: ' + str(quality))
            stage = 'sections-' + str(per_wave)
            save_faces(folder, stage, q, f, k, palette, np.array(ids))
            variants.append({'sections_per_wave': per_wave, 'triangles': len(f), 'placed_triangles': len(f) * c['placed_uses'],
                             'sampled_deviation_mm': quality, 'proof': proof, 'glb_sha256': digest(folder / (stage + '.glb'))})
            print(cid, per_wave, len(t), '->', len(f), quality, flush=True)
        rows.append({'id': cid, 'source_step_sha256': digest(source), 'reference_triangles': len(t), 'uses': c['placed_uses'], 'variants': variants})
    report = {'source_sha256': audit['source_sha256'], 'components': rows,
              'producer_sha256': digest(__file__), 'pass_sha256': digest(ROOT / 'python/cad_extrusion_skin.py'),
              'scope': 'Four road components only. Native shared boundaries resampled for all adjoining caps. Separate visual/collision inspection candidates; no installed asset or rule detector changes.'}
    (args.out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
