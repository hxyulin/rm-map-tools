#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Package a complete source-pose robot with audited assembly names and original materials."""
import argparse
import copy
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, write_glb, mesh_instances


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--recipe', type=Path, default=Path(__file__).with_name('candidates.json'))
    parser.add_argument('source_id')
    args = parser.parse_args()
    source = json.loads(args.recipe.read_text())['sources'][args.source_id]
    name = source['source_model_id'];folder = args.sources / (name + '-pilot')
    assert digest(args.sources / (name + '.step')) == source['cad_sha256']
    document, binary = read_glb(folder / 'low.glb')
    original_materials = json.dumps(document['materials'], sort_keys=True)
    original_meshes = json.dumps(document['meshes'], sort_keys=True)
    original_nodes = [(i, n) for i, n in enumerate(document['nodes']) if 'mesh' in n]
    rows = json.loads((args.sources / (name + '-hierarchy.json')).read_text())
    owners = defaultdict(list)
    for row in rows:
        for sid in row.get('native_solids', []):
            owners[sid].append(row['path'])
    groups = {}
    for row in rows:
        groups[row['path']] = len(document['nodes'])
        document['nodes'].append({'name': row['name'], 'children': [],
                                  'extras': {'source_occurrence_path': row['path'],
                                             'source_occurrence_name': row['occurrence_name']}})
    for row in rows:
        document['nodes'][groups[row['path']]]['children'] += [groups[c] for c in row.get('children', [])]
    root_children = [groups[r['path']] for r in rows if '/' not in r['path']]
    unclassified = []
    for i, node in original_nodes:
        sid = node['extras']['native_solid_index']
        node['extras']['source_occurrence_paths'] = owners[sid]
        # Coincident source aliases share the already unique cooked native solid.
        if owners[sid]:
            document['nodes'][groups[owners[sid][0]]]['children'].append(i)
        else:
            root_children.append(i);unclassified.append(sid)
    points = np.concatenate([p for ni, pi, p, t, m in mesh_instances(document, binary)])
    rotation = np.asarray(source['review_rotation']);assert np.linalg.det(rotation) > .999
    rotated = points @ rotation.T;lo = rotated.min(0);hi = rotated.max(0)
    matrix = np.eye(4);matrix[:3, :3] = rotation
    matrix[:3, 3] = [-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2]
    document['nodes'][0]['children'] = root_children
    document['nodes'][0]['matrix'] = matrix.flatten(order='F').tolist()
    document['asset']['extras'] = {'source': source, 'scope': 'Complete source-pose visual candidate; joints and physics are unbound.'}
    # Packaging changes only scene hierarchy and its rigid root frame.
    assert json.dumps(document['materials'], sort_keys=True) == original_materials
    assert json.dumps(document['meshes'], sort_keys=True) == original_meshes
    referenced = [child for n in document['nodes'] for child in n.get('children', [])]
    assert all(referenced.count(i) == 1 for i, n in original_nodes)
    out = folder / 'package';out.mkdir(exist_ok=True)
    write_glb(out / 'model.glb', document, binary)
    check, payload = read_glb(out / 'model.glb');assert payload == binary
    source_triangles = sum(len(t) for ni, pi, p, t, m in mesh_instances(*read_glb(folder / 'low.glb')))
    placed_triangles = sum(len(t) for ni, pi, p, t, m in mesh_instances(check, payload))
    assert source_triangles == placed_triangles
    styled = copy.deepcopy(document)
    changed_materials = 0
    for material in styled['materials']:
        extras = material.get('extras', {})
        eligible = ((extras.get('step_colour_origin') == 'fallback' and extras.get('step_colour_srgb') is None)
                    or (extras.get('step_colour_origin') == 'source' and extras.get('step_colour_srgb') == [.7922, .8196, .9333]))
        if not eligible:
            continue
        extras['display_override'] = {'policy': 'user-selected-graphite-v1',
                                     'original_pbr': copy.deepcopy(material['pbrMetallicRoughness'])}
        def linear(v):
            return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
        material['pbrMetallicRoughness'].update(baseColorFactor=[*[linear(v) for v in [.095, .10, .11]], 1.],
                                                metallicFactor=.1, roughnessFactor=.45)
        changed_materials += 1
    write_glb(out / 'graphite.glb', styled, binary)
    manifest = {'schema': 'robot-candidate-v1', 'source': source,
                'producer_sha256': digest(Path(__file__)), 'recipe_sha256': digest(args.recipe),
                'inputs': {'low.glb': digest(folder / 'low.glb'),
                           'hierarchy.json': digest(args.sources / (name + '-hierarchy.json'))},
                'files': {n: digest(out / n) for n in ['model.glb', 'graphite.glb']},
                'graphite_override_materials': changed_materials,
                'placed_triangles': placed_triangles, 'source_solid_groups': len(original_nodes),
                'assembly_groups': len(rows), 'unclassified_native_solids': sorted(set(unclassified)),
                'dimensions_gltf_m': (hi - lo).tolist(),
                'geometry_binary_preserved': True, 'source_materials_preserved': True,
                'scope': 'Review candidate only; not a fitted simulator chassis profile.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    notice = f"# Source-derived robot candidate\n\n{source['credit']}\n\n{source['source_article']}\n\n{source['terms']}\n\n"
    notice += ('Original geometry/materials remain third-party CAD. The simulator software license does not relicense them. '
               'Simplified visual candidate only; no inferred joints, mass/inertia, robot compliance or collision/scoring eligibility.\n')
    (out / 'CAD-NOTICE.md').write_text(notice)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
