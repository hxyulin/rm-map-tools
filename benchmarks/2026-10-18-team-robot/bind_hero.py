#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Bind the source Hero's folding arm, firing pitch and four mecanum wheels."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, write_glb, mesh_instances
from export_field_package import GlbWriter

FLOOR = .090955198030338
PIVOT = np.array([0., .122 + FLOOR, 0.])
TIP = np.array([0., .23647 + FLOOR, -.0091])
ORIGINS = {'body': [0, 0, 0], 'yaw': [0, .076 + FLOOR, 0],
           'fold': PIVOT.tolist(), 'pitch': TIP.tolist(),
           'wheel-0': [.27505, -.0119 + FLOOR, .29],
           'wheel-1': [-.27505, -.0119 + FLOOR, .29],
           'wheel-2': [.27499, -.013955 + FLOOR, -.244978],
           'wheel-3': [-.27499, -.013955 + FLOOR, -.244978]}
PARENTS = {'body': None, 'yaw': 'body', 'fold': 'yaw', 'pitch': 'fold',
           **{f'wheel-{i}': 'body' for i in range(4)}}
WHEELS = {'1/4/3': 'wheel-0', '1/6/2': 'wheel-1', '1/2/16': 'wheel-2', '1/5/17': 'wheel-3'}
HEAD = {9, 10, 11, 12, 13, 14, 15, 16, 22, 23, 27, 28, 29}
ARM = {1, 6, 7, 8, 17, 24}


def group(path):
    for prefix, name in WHEELS.items():
        if path == prefix or path.startswith(prefix + '/'):
            return name
    if not path.startswith('1/32/'):
        return 'body'
    if path.startswith('1/32/21/1'):
        return 'fold'
    if path.startswith('1/32/21/2'):
        return 'pitch'
    part = int(path.split('/')[2])
    return 'pitch' if part in HEAD else 'fold' if part in ARM else 'yaw'


def rotation(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--prepared',type=Path)
    a = p.parse_args()
    recipe = json.loads(Path(__file__).with_name('candidates.json').read_text())['sources']['hero']
    folder = a.sources;model_id = recipe['source_model_id']
    source = folder / (model_id + '.step')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == recipe['cad_sha256']
    prepared=a.prepared or folder
    hierarchy = json.loads((prepared / (model_id + '-hierarchy.json')).read_text())
    owners = {}
    for row in hierarchy:
        for sid in row.get('native_solids', []):owners.setdefault(sid, row['path'])
    document, binary = read_glb(prepared / (model_id + '-pilot') / 'low.glb')
    center = np.array(json.loads((prepared / (model_id + '-frame.json')).read_text())['source_center_mm']) / 1000
    transform = np.array(recipe['review_rotation'])
    parts = []
    for ni, pi, points, triangles, material in mesh_instances(document, binary):
        node = document['nodes'][ni];sid = node['extras']['native_solid_index']
        path = node['extras'].get('source_leaf_path') or owners.get(sid, '');link = group(path)
        position = (points + center) @ transform.T + [0, FLOOR, 0]
        mat = document['materials'][material]
        color = None if mat['extras']['step_colour_srgb'] is None else mat['name'].removeprefix('colour_')
        parts.append((node['name'] + f'-{pi}', link, position - ORIGINS[link], triangles, color,
                      {**node['extras'], 'source_occurrence_path': path, 'motion_group': link, 'articulation_bound': True}))
    a.out.mkdir(parents=True, exist_ok=True)
    stats = {}
    for pose, angle in [('neutral', 0), ('mid-fold', 63.5), ('folded', 127)]:
        angle = math.radians(angle)
        writer = GlbWriter('artisans-folding-hero', {'version': '2.0', 'copyright': recipe['credit'] + '; original source CAD terms apply.'})
        groups = {}
        geometry = []
        for name, link, points, triangles, color, extras in parts:
            before = len(writer.nodes)
            writer.add_node(name, points, triangles, [color] * len(triangles), extras=extras)
            groups.setdefault(link, []).extend(range(before + 1, len(writer.nodes) + 1))
            origin = np.array(ORIGINS[link])
            if link == 'fold':world = points @ rotation(angle).T + PIVOT
            elif link == 'pitch':world = points + PIVOT + rotation(angle) @ (TIP - PIVOT)
            else:world = points + origin
            geometry.append(world)
        path = a.out / (pose + '.glb');writer.write(path);d, b = read_glb(path)
        indices = {}
        for link in ORIGINS:
            index = len(d['nodes']);indices[link] = index;parent = PARENTS[link]
            offset = np.array(ORIGINS[link]) - (np.array(ORIGINS[parent]) if parent else 0)
            coordinate = angle if link == 'fold' else -angle if link == 'pitch' else 0
            d['nodes'].append({'name': 'link/' + link, 'translation': offset.tolist(),
                               'rotation': [math.sin(coordinate / 2), 0, 0, math.cos(coordinate / 2)],
                               'children': groups.get(link, [])})
            if parent:d['nodes'][indices[parent]]['children'].append(index)
        d['nodes'][0]['children'] = [indices['body']]
        write_glb(path, d, b)
        geometry = np.concatenate(geometry)
        stats[pose] = {'angle_deg': math.degrees(angle), 'bounds_gltf_m': [geometry.min(0).tolist(), geometry.max(0).tolist()],
                       'triangles': sum(len(part[3]) for part in parts)}
    manifest = {'schema': 2, 'profile': 'artisans-folding-hero-v1', 'source': recipe,
                'files': {'neutral': {'file': 'neutral.glb', 'sha256': hashlib.sha256((a.out / 'neutral.glb').read_bytes()).hexdigest()}},
                'producer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'prepared_visual_sha256': hashlib.sha256((prepared / (model_id + '-pilot') / 'low.glb').read_bytes()).hexdigest(),
                'prepared_hierarchy_sha256': hashlib.sha256((prepared / (model_id + '-hierarchy.json')).read_bytes()).hexdigest(),
                'link_origins_gltf_m': ORIGINS, 'body_origin_y_m': FLOOR + .0775, 'poses': stats,
                'policy': 'Source-fitted joint centres; 127 degree fold endpoint and actuator rate are simulator assumptions. No actuator torque/leg linkage model.'}
    (a.out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (a.out / 'CAD-NOTICE.md').write_text(recipe['credit'] + '\n' + recipe['source_article'] + '\n' + recipe['terms'] + '\n')
    print(json.dumps(stats, indent=2))


if __name__ == '__main__':main()
