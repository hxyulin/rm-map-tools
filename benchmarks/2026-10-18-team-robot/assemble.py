#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose source-derived robot meshes into explicit rigid motion groups.

The recipe pins source CAD, cooked GLBs and source occurrence membership. Output
is a visual prototype, not a collision model, mass estimate or mechanical design.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from export_field_package import GlbWriter
from gltf_scene import mesh_instances, read_glb, write_glb


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rotation(axis, angle):
    axis = np.asarray(axis, float)
    if axis.shape != (3,) or not np.isfinite(axis).all() or not np.isclose(axis @ axis, 1):
        raise ValueError('joint axis must be a finite unit vector')
    x, y, z = axis
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + math.sin(angle) * skew + (1 - math.cos(angle)) * (skew @ skew)


def frames(links, coordinates=None):
    """Resolve explicit coordinates and mimic joints, without a physics engine."""
    coordinates = coordinates or {}
    known = {v['coordinate'] for v in links.values() if 'coordinate' in v}
    if set(coordinates) - known or any(not math.isfinite(v) for v in coordinates.values()):
        raise ValueError('unknown or nonfinite joint coordinate')
    result = {}
    for name, link in links.items():
        parent = link['parent']
        if parent is not None and parent not in result:
            raise ValueError('links must be ordered parent first')
        pose = np.eye(4)
        origin = np.asarray(link['origin_gltf_m'], float)
        if origin.shape != (3,) or not np.isfinite(origin).all():
            raise ValueError('invalid joint origin')
        pose[:3, 3] = origin - (np.asarray(links[parent]['origin_gltf_m']) if parent else 0)
        if 'axis' in link:
            q = coordinates.get(link['coordinate'], 0) * link.get('multiplier', 1)
            pose[:3, :3] = rotation(link['axis'], q)
        result[name] = (result[parent] if parent else np.eye(4)) @ pose
    return result


def select(path, rules, default):
    matches = [r for r in rules if path == r['path'] or path.startswith(r['path'] + '/')]
    return max(matches, key=lambda r: len(r['path']))['link'] if matches else default


def box_mesh(lower, upper):
    p = np.array([[x, y, z] for x in [lower[0], upper[0]]
                  for y in [lower[1], upper[1]] for z in [lower[2], upper[2]]])
    t = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                  [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                  [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return p, t


def collect(source_root, recipe):
    """Import each source solid exactly once; retain source colors and provenance."""
    parts, inventory = [], {}
    for source_id, source in recipe['sources'].items():
        files = {}
        for key in ['visual', 'hierarchy']:
            path = (source_root / source[key]['file']).resolve()
            if not path.is_relative_to(source_root.resolve()) or digest(path) != source[key]['sha256']:
                raise ValueError('source input path/checksum mismatch: ' + source_id + '/' + key)
            files[key] = path
        hierarchy = json.loads(files['hierarchy'].read_text())
        membership = {}
        for item in hierarchy:
            for sid in item.get('native_solids', []):
                if not sid or sid in membership:
                    raise ValueError('ambiguous source solid occurrence')
                membership[sid] = item
        document, binary = read_glb(files['visual'])
        seen, kept, omitted = set(), set(), set()
        for ni, pi, p, t, material in mesh_instances(document, binary):
            extra = document['nodes'][ni]['extras']
            if extra['source_sha256'] != source['cad_sha256']:
                raise ValueError('cooked geometry names a different STEP')
            sid = extra['native_solid_index']
            seen.add(sid)
            # Non-solid group 0 in the gimbal is an omitted lower-tray PCB.
            if sid == 0:
                if source.get('omit_non_solid_group') is not True:
                    raise ValueError('unbound source surface group')
                omitted.add(sid)
                continue
            if sid not in membership:
                raise ValueError('source solid missing from hierarchy')
            item = membership[sid]
            link = select(item['path'], source['rules'], source['default_link'])
            if link is None:
                omitted.add(sid)
                continue
            if link not in recipe['links']:
                raise ValueError('unknown motion group')
            kept.add(sid)
            world = p + np.asarray(source['source_center_mm']) / 1000 + source['translation_gltf_m']
            local = world - recipe['links'][link]['origin_gltf_m']
            mat = document['materials'][material]
            if 'step_colour_srgb' not in mat.get('extras', {}):
                raise ValueError('source material lacks original sRGB/fallback provenance')
            srgb = mat['extras']['step_colour_srgb']
            color = None if srgb is None else mat['name'].removeprefix('colour_')
            if srgb is not None and not np.array_equal(list(map(float, color.split(','))), srgb):
                raise ValueError('source material name/color provenance mismatch')
            parts.append({'name': source_id + '/' + item['path'] + '/solid-' + str(sid) + '/primitive-' + str(pi),
                          'points': local, 'triangles': t, 'color': color, 'link': link,
                          'extras': {**extra, 'source_id': source_id, 'source_occurrence_path': item['path'],
                                     'source_definition_name': item['name'], 'motion_group': link,
                                     'articulation_bound': True, 'collision_eligible': False}})
        if kept & omitted or (set(membership) - seen):
            raise ValueError('source coverage is incomplete or overlapping')
        inventory[source_id] = {'retained_solids': sorted(kept), 'omitted_solids': sorted(omitted),
                                'placed_triangles': sum(len(p['triangles']) for p in parts if p['extras'].get('source_id') == source_id)}
    for i, spec in enumerate(recipe.get('adapter_posts', [])):
        p, t = box_mesh(spec['lower_gltf_m'], spec['upper_gltf_m'])
        parts.append({'name': 'integration/adapter-post-' + str(i), 'points': p, 'triangles': t,
                      'color': '0.65,0.65,0.65', 'link': 'body',
                      'extras': {'motion_group': 'body', 'origin': 'simulator integration adapter, not source CAD',
                                 'collision_eligible': False}})
    return parts, inventory


def export(path, parts, recipe, coordinates=None):
    """Rebase source geometry into rigid links; static pose exports share the recipe."""
    poses = frames(recipe['links'], coordinates)
    writer = GlbWriter('team-omni-prototype', {'version': '2.0',
                          'copyright': recipe['credit'], 'extras': {'frame': recipe['frame'],
                          'scope': 'Source-derived visual prototype; original CAD terms apply; no collision or mass model.'}})
    groups = {}
    for part in parts:
        before = len(writer.nodes)
        writer.add_node(part['name'], part['points'], part['triangles'],
                        [part['color']] * len(part['triangles']), extras=part['extras'])
        groups.setdefault(part['link'], []).extend(range(before + 1, len(writer.nodes) + 1))
    writer.write(path)
    d, b = read_glb(path)
    indices = {}
    for name, spec in recipe['links'].items():
        index = len(d['nodes']);indices[name] = index
        parent = spec['parent']
        matrix = np.linalg.inv(poses[parent]) @ poses[name] if parent else poses[name]
        node = {'name': 'link/' + name, 'matrix': matrix.flatten(order='F').tolist(),
                'children': groups.get(name, []), 'extras': {'motion_group': name, 'binding': spec}}
        d['nodes'].append(node)
        if parent:d['nodes'][indices[parent]]['children'].append(index)
    d['nodes'][0]['children'] = [indices[n] for n, s in recipe['links'].items() if s['parent'] is None]
    write_glb(path, d, b)
    return indices


def animate(path, parts, recipe):
    """Bake a six-second inspection loop, including the pitch linkage mimics."""
    indices = export(path, parts, recipe)
    document, binary = read_glb(path)
    payload = bytearray(binary)

    def add(values, kind):
        values = np.asarray(values, dtype='<f4')
        payload.extend(b'\0' * (-len(payload) % 4))
        offset = len(payload);payload.extend(values.tobytes())
        view = len(document['bufferViews'])
        document['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': values.nbytes})
        index = len(document['accessors'])
        accessor = {'bufferView': view, 'componentType': 5126, 'count': len(values), 'type': kind}
        if kind == 'SCALAR':accessor.update(min=[float(values.min())], max=[float(values.max())])
        document['accessors'].append(accessor)
        return index

    times = np.linspace(0, 6, 73)
    time_accessor = add(times, 'SCALAR')
    animation = {'name': 'Inspection — yaw, pitch linkage and wheel spin', 'samplers': [], 'channels': []}
    for name, link in recipe['links'].items():
        if 'axis' not in link:continue
        node = document['nodes'][indices[name]]
        local = np.asarray(node.pop('matrix')).reshape(4, 4, order='F')
        node['translation'] = local[:3, 3].tolist()
        node['rotation'] = [0, 0, 0, 1]
        coordinate = link['coordinate']
        if coordinate.startswith('wheel_'):
            angles = times * math.pi
        else:
            angles = np.interp(times, [0, 2, 4, 6], [0, .6, -.6, 0] if coordinate == 'yaw_rad' else [0, .35, -.2, 0])
        angles *= link.get('multiplier', 1)
        rotations = np.column_stack((np.sin(angles / 2)[:, None] * link['axis'], np.cos(angles / 2)))
        sampler = len(animation['samplers'])
        animation['samplers'].append({'input': time_accessor, 'output': add(rotations, 'VEC4'), 'interpolation': 'LINEAR'})
        animation['channels'].append({'sampler': sampler, 'target': {'node': indices[name], 'path': 'rotation'}})
    document['animations'] = [animation]
    document['buffers'][0]['byteLength'] = len(payload)
    write_glb(path, document, bytes(payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--recipe', type=Path, default=Path(__file__).with_name('recipe.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    parts, inventory = collect(args.sources, recipe)
    if args.out.exists():raise ValueError('output directory must be new')
    args.out.mkdir(parents=True)
    for name, coordinates in recipe['review_poses'].items():
        export(args.out / (name + '.glb'), parts, recipe, coordinates)
    animate(args.out / 'animated.glb', parts, recipe)
    manifest = {'schema': 1, 'recipe_sha256': digest(args.recipe), 'producer_sha256': digest(__file__),
                'frame': recipe['frame'], 'sources': recipe['sources'], 'links': recipe['links'],
                'inventory': inventory, 'placed_triangles': sum(len(p['triangles']) for p in parts),
                'files': {n: {'file': n + '.glb', 'sha256': digest(args.out / (n + '.glb'))} for n in [*recipe['review_poses'], 'animated']},
                'scope': recipe['scope'], 'credit': recipe['credit']}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (args.out / 'CAD-NOTICE.md').write_text(recipe['notice'] + '\n')
    print(json.dumps({'placed_triangles': manifest['placed_triangles'], 'inventory': {k: {n: len(v) if isinstance(v, list) else v for n, v in x.items()} for k, x in inventory.items()}}, indent=2))


if __name__ == '__main__':
    main()
