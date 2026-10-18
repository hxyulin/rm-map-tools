#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Package source robot hardware with audited names, original materials and reviewed helper exclusions."""
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
from robot_reference_geometry import apply_reference_exclusions, verify_reference_cleanup, compact_reference_resources


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attach_source_meshes(document, rows):
    """Attach located meshes once, including open shells with audited leaf paths.

    Occurrence nodes carry names/provenance only: cooked vertices already include
    source placements, so applying occurrence transforms again would move them twice.
    """
    original_nodes = [(i, n) for i, n in enumerate(document['nodes']) if 'mesh' in n]
    owners = defaultdict(list)
    leaf_paths = {row['path'] for row in rows if 'children' not in row}
    for row in rows:
        for sid in row.get('native_solids', []):
            if sid > 0:
                owners[sid].append(row['path'])
    groups = {}
    for row in rows:
        if row['path'] in groups:
            raise ValueError('duplicate source occurrence path')
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
        shell_path = node['extras'].get('source_leaf_path')
        if shell_path is not None and (sid != 0 or shell_path not in leaf_paths):
            raise ValueError('shell must name an audited non-solid leaf')
        paths = [shell_path] if shell_path is not None else owners[sid]
        node['extras']['source_occurrence_paths'] = paths
        # Coincident aliases retain all paths but attach their unique cooked mesh once.
        if paths:
            document['nodes'][groups[paths[0]]]['children'].append(i)
        else:
            root_children.append(i)
            unclassified.append(sid)
    document['nodes'][0]['children'] = root_children
    referenced = [child for n in document['nodes'] for child in n.get('children', [])]
    if not all(referenced.count(i) == 1 for i, _ in original_nodes):
        raise ValueError('source mesh ownership must be complete and unique')
    return unclassified


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
    unclassified = attach_source_meshes(document, rows)
    points = np.concatenate([p for ni, pi, p, t, m in mesh_instances(document, binary)])
    rotation = np.asarray(source['review_rotation']);assert np.linalg.det(rotation) > .999
    rotated = points @ rotation.T;lo = rotated.min(0);hi = rotated.max(0)
    matrix = np.eye(4);matrix[:3, :3] = rotation
    matrix[:3, 3] = [-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2]
    document['nodes'][0]['matrix'] = matrix.flatten(order='F').tolist()
    document['asset']['extras'] = {'source': source, 'scope': 'Complete source-pose visual candidate; joints and physics are unbound.'}
    # Packaging changes only scene hierarchy and its rigid root frame.
    assert json.dumps(document['materials'], sort_keys=True) == original_materials
    assert json.dumps(document['meshes'], sort_keys=True) == original_meshes
    referenced = [child for n in document['nodes'] for child in n.get('children', [])]
    assert all(referenced.count(i) == 1 for i, n in original_nodes)
    original_binary = binary
    original_geometry = copy.deepcopy(document)
    center = json.loads((args.sources / (name + '-frame.json')).read_text())['source_center_mm'] if source.get('reference_exclusions') else None
    binary, excluded = apply_reference_exclusions(document, binary, rows, source.get('reference_exclusions', []), center)
    assert binary[:len(original_binary)] == original_binary
    assert json.dumps(document['materials'], sort_keys=True) == original_materials
    if excluded:
        binary = compact_reference_resources(document, binary)
    physical_points = np.concatenate([p for ni, pi, p, t, m in mesh_instances(document, binary)])
    out = folder / 'package';out.mkdir(exist_ok=True)
    write_glb(out / 'model.glb', document, binary)
    check, payload = read_glb(out / 'model.glb');assert payload == binary
    validation = verify_reference_cleanup(original_geometry, original_binary, check, payload, excluded)
    source_triangles = sum(len(t) for ni, pi, p, t, m in mesh_instances(*read_glb(folder / 'low.glb')))
    placed_triangles = sum(len(t) for ni, pi, p, t, m in mesh_instances(check, payload))
    assert source_triangles - sum(r['removed_triangles'] for r in excluded) == placed_triangles
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
                'placed_triangles': placed_triangles,
                'source_solid_groups': sum(n['extras']['native_solid_index'] > 0 for _, n in original_nodes),
                'source_shell_groups': sum(n['extras'].get('source_leaf_path') is not None for _, n in original_nodes),
                'assembly_groups': len(rows), 'unclassified_native_solids': sorted(set(unclassified)),
                'dimensions_gltf_m': np.ptp(physical_points, axis=0).tolist(),
                'source_pose_dimensions_gltf_m': (hi - lo).tolist(),
                'reference_geometry_exclusions': excluded,
                'reference_geometry_validation': validation,
                'reference_pass_sha256': digest(ROOT / 'python/robot_reference_geometry.py'),
                'geometry_binary_preserved': not bool(excluded), 'original_buffer_bytes_preserved': not bool(excluded),
                'retained_attribute_bytes_preserved': True, 'unused_reference_resources_pruned': bool(excluded),
                'retained_physical_surfaces_unchanged': True, 'source_materials_preserved': True,
                'scope': 'Physical-geometry review candidate; reviewed CAD reference bodies excluded; not a fitted simulator chassis profile.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    notice = f"# Source-derived robot candidate\n\n{source['credit']}\n\n{source['source_article']}\n\n{source['terms']}\n\n"
    notice += ('Original geometry/materials remain third-party CAD. The simulator software license does not relicense them. '
               'Simplified visual candidate only; no inferred joints, mass/inertia, robot compliance or collision/scoring eligibility.\n')
    if excluded:
        notice += '\nExcluded CAD reference geometry (original source remains intact):\n'
        for row in excluded:
            notice += f"- {row['path']} / {row['name']}: {row['reason']} ({row['removed_triangles']} triangles).\n"
    (out / 'CAD-NOTICE.md').write_text(notice)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
