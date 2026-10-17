#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build a complete instanced GLB without flattening source hierarchy or artwork."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_glb_composition import RigidComposer
from gltf_scene import read_glb, write_glb, scene_nodes
from plan_cad_lods import build_plan, digest, multiply


def placed_triangles(doc):
    return sum(sum((doc['accessors'][p['indices']]['count'] if 'indices' in p else doc['accessors'][p['attributes']['POSITION']]['count']) // 3
                   for p in doc['meshes'][doc['nodes'][index]['mesh']]['primitives'])
               for index, world, parent in scene_nodes(doc) if 'mesh' in doc['nodes'][index])


def build(folder, summary, hierarchy, stage):
    composer = RigidComposer(); d = composer.document; definitions = {}; records = []
    for row in summary['components']:
        path = ROOT / row[stage + '_glb']
        if digest(path) != row[stage + '_sha256']: raise ValueError('composition input changed')
        doc, binary = read_glb(path)
        record = composer.append_definition(row['id'], doc, binary)
        records.append({'id': row['id'], 'source_glb_sha256': digest(path), **record})
        definitions[row['id']] = row
    plan = build_plan(hierarchy); assemblies = {a['product_id']: a for a in hierarchy['assemblies']}
    floor = json.loads((ROOT / 'out/rmuc2027-terrain-cost-full/audit.json').read_bytes())
    bounds = np.array(next(c for c in floor['components'] if c['id'] == 'floor/body-23736')['bbox_mm'])
    origin = np.r_[(bounds[0, :2] + bounds[1, :2]) / 2, bounds[1, 2]] / 1000
    yup = np.array([[1., 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]])
    centre = np.eye(4); centre[:3, 3] = -origin
    display = yup @ centre
    d['nodes'].append({'name': 'field-inspection-frame', 'matrix': display.ravel(order='F').tolist(),
                       'extras': {'source_origin_m': origin.tolist(), 'inspection_only': True}})
    d['scenes'][0]['nodes'] = [0]; mapping = {}; source_nodes = {n['id']: n for n in plan['nodes']}
    for node in plan['nodes']:
        parent = node['parent']; local = np.eye(4)
        if parent is not None:
            slot = int(node['id'].rsplit('/', 1)[1].split('-p')[0])
            local = np.array(assemblies[source_nodes[parent]['product_id']]['children'][slot]['matrix_mm'])
            if multiply(source_nodes[parent]['world_matrix_mm'], local.tolist()) != node['world_matrix_mm']:
                raise ValueError('source local placement mismatch')
        local[:3, 3] /= 1000
        index = len(d['nodes']); mapping[node['id']] = index
        d['nodes'].append({'name': node['name'], 'matrix': local.ravel(order='F').tolist(),
                           'extras': {'source_hierarchy_node_id': node['id'], 'source_product_id': node['product_id'],
                                      'component_id': node['component_id'], 'inspection_only': True}})
        d['nodes'][mapping[parent] if parent else 0].setdefault('children', []).append(index)
        if node['component_id']:
            composer.instantiate(node['component_id'], index,
                                 extras={'composition_occurrence': {'node_id': node['id'], 'component_id': node['component_id']}})
    expected = summary['reference_placed_triangles'] if stage == 'reference' else summary['candidate_placed_triangles']
    if placed_triangles(d) != expected: raise ValueError('assembled placed count differs')
    worlds = {i: matrix for i, matrix, _ in scene_nodes(d)}
    for node in plan['nodes']:
        expected_pose = np.array(node['world_matrix_mm']); expected_pose[:3, 3] /= 1000
        if not np.allclose(worlds[mapping[node['id']]], display @ expected_pose, atol=1e-10, rtol=0):
            raise ValueError('exported hierarchy placement changed')
    target = folder / (stage + '-field.glb'); write_glb(target, d, composer.binary)
    check, blob = read_glb(target)
    if placed_triangles(check) != expected: raise ValueError('written placed count differs')
    return {'stage': stage, 'placed_triangles': expected, 'mesh_definitions': len(d['meshes']),
            'stored_mesh_triangles': sum(sum((d['accessors'][p['indices']]['count'] if 'indices' in p else d['accessors'][p['attributes']['POSITION']]['count']) // 3 for p in mesh['primitives']) for mesh in d['meshes']),
            'primitive_definitions': sum(len(m['primitives']) for m in d['meshes']),
            'hierarchy_nodes_verified': len(plan['nodes']), 'component_uses': sum(n['component_id'] is not None for n in plan['nodes']),
            'embedded_images': len(d['images']), 'bytes': target.stat().st_size,
            'glb_sha256': digest(target), 'definitions': records}


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); out = a.out.resolve(); summary_path = out / 'summary.json'; summary = json.loads(summary_path.read_bytes())
    hp = ROOT / 'out/rmuc2027-hierarchy/hierarchy.json'
    if not summary['complete'] or digest(hp) != summary['hierarchy_sha256']: raise ValueError('incomplete or changed hierarchy')
    hierarchy = json.loads(hp.read_bytes()); results = [build(out, summary, hierarchy, s) for s in ['reference', 'candidate']]
    report = {'summary_sha256': digest(summary_path), 'stages': results,
              'producer_sha256': {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), ROOT / 'python/cad_glb_composition.py']},
              'scope': 'All 116 definitions / 171 occurrences. Original source hierarchy local transforms retained, one display root rebases and converts to Y-up. Every definition imported once, meshes/buffers shared across copies. Embedded artwork and all vertex attributes retained. Inspection composition, no animation/physics/runtime installation.'}
    (out / 'assembly.json').write_text(json.dumps(report, indent=2) + '\n')
    print([{k: v for k, v in r.items() if k != 'definitions'} for r in results], flush=True)

if __name__ == '__main__': main()
