#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verify face runs, exported triangles, retained faces and visual-only roles."""
import argparse
import json
from pathlib import Path
from run import ROOT
import numpy as np
from cad_collision_roles import CollisionRoles
from gltf_scene import read_glb, mesh_instances
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); out = args.out.resolve(); roads = json.loads((out / 'summary.json').read_bytes()); rows = []
    roles_path = ROOT / 'rules/roles-rmuc2027-terrain.json'
    roles = CollisionRoles.read(roles_path, ROOT / 'out/rmuc2027-hierarchy/hierarchy.json')
    for row in roads['components']:
        folder = out / row['id']; before = np.load(folder / 'reference.npz')
        for variant in row['variants']:
            stage = 'sections-' + str(variant['sections_per_wave']); path = folder / (stage + '.glb')
            if digest(path) != variant['glb_sha256']: raise ValueError('road GLB changed')
            mesh = np.load(folder / (stage + '.npz')); p, t, m, ids = [mesh[k] for k in ['positions_mm', 'triangles', 'material_ids', 'source_face_ids']]
            palette = mesh['palette']; doc, blob = read_glb(path); seen = 0
            for node, pi, q, f, mi in mesh_instances(doc, blob):
                if sum('mesh' in n for n in doc['nodes']) != 1: raise ValueError('rigid road was not material batched')
                prim = doc['meshes'][doc['nodes'][node]['mesh']]['primitives'][pi]; color = doc['materials'][mi]['extras']['step_colour_srgb']
                key = None if color is None else ','.join(f'{x:.4f}' for x in color)
                colors = [str(v) or None for v in palette.tolist()]; selected = m == colors.index(key)
                expected = (p[t[selected]] / 1000).astype(np.float32).astype(float)
                if not np.array_equal(q[f], expected): raise ValueError('exported triangle order/positions differ')
                actual_ids = np.empty(len(f), dtype=np.int64); expected_start = 0
                for run in prim['extras']['source_native_face_runs']:
                    if run['first_triangle'] != expected_start: raise ValueError('face runs have gaps/overlap')
                    end = expected_start + run['triangle_count']; actual_ids[expected_start:end] = run['source_face_index']; expected_start = end
                if expected_start != len(f) or not np.array_equal(actual_ids, ids[selected]): raise ValueError('source face runs differ')
                seen += len(f)
            if seen != len(t): raise ValueError('export count differs')
            changed = set(variant['proof']['selected_native_faces']) | {c['native_face_index'] for c in variant['proof']['neighbor_caps']}
            retained = 0
            for fi in set(ids) - changed:
                a = before['source_face_ids'] == fi; b = ids == fi
                if not np.array_equal(before['positions_mm'][before['triangles'][a]], p[t[b]]) or not np.array_equal(before['material_ids'][a], m[b]): raise ValueError('unselected native face changed')
                retained += int(b.sum())
            rows.append({'id': row['id'], 'sections_per_wave': variant['sections_per_wave'], 'exported_triangles': len(t), 'retained_face_triangles_exact': retained,
                         'face_runs_exact': True, 'one_rigid_mesh': True, 'collision_enabled': roles.collision_enabled(row['id'])})
    composition = json.loads((out / 'composition.json').read_bytes())
    unchanged = [r for r in composition['components'] if r['candidate_sha256'] == r['reference_sha256']]
    if len(unchanged) != 112: raise ValueError('unexpected changed definition')
    for r in unchanged:
        if digest(ROOT / r['candidate_glb']) != r['reference_sha256']: raise ValueError('retained approved equipment changed')
    assembly = json.loads((out / 'assembly.json').read_bytes())
    for r in assembly['stages']:
        if digest(out / (r['stage'] + '-field.glb')) != r['glb_sha256']: raise ValueError('complete field changed')
    result = {'roads': rows, 'unchanged_approved_definition_hashes': len(unchanged), 'collision_roles_sha256': digest(roles_path),
              'road_collision_triangles_12_sections': sum(v['triangles'] * r['uses'] for r in roads['components'] if roles.collision_enabled(r['id']) for v in r['variants'] if v['sections_per_wave'] == 12),
              'road_summary_sha256': digest(out / 'summary.json'), 'composition_sha256': digest(out / 'composition.json'), 'producer_sha256': digest(__file__)}
    if result['road_collision_triangles_12_sections'] != 1892: raise ValueError('road collision count changed')
    (out / 'validation.json').write_text(json.dumps(result, indent=2) + '\n'); print('verified', len(rows), 'road variants;', len(unchanged), 'definitions byte retained')


if __name__ == '__main__': main()
