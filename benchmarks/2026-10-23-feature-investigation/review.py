# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render source-bound feature trials with matched cameras and actual counts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image
from gltf_scene import read_glb, scene_nodes
from simplify_package import scene_triangles


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=Path(__file__).with_name('plan.json'))
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-feature-investigation')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(args.plan.read_text())
    render = module('runtime_trial_render', 'benchmarks/2026-10-23-runtime-opportunities/render.py')
    raster = render.module('feature_raster', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
    asset_rows = {}
    reference_inputs = []
    package = local(plan.get('package', '../rm-simulator/field-2027'))
    baseline = ROOT / 'out/rmuc2027-runtime-opportunities'
    refined = json.loads((baseline / 'refined.json').read_text())
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = package / relative
        for name, row in json.loads(manifest.read_text())['assets'].items():
            asset_rows[name] = row
            source = manifest.parent / row['visual']
            if digest(source) != row['visual_sha256']:
                raise ValueError('installed camera source hash mismatch')
            reference_inputs.append((name, source, row['placements_in_source_arena_frame']))
    paths = {}
    report = {'plan_sha256': digest(args.plan), 'levels': [], 'views': [],
              'scope': 'Actual feature-trial GLBs, matched 1200px two-sided source-color diagnostics. Intentional losses are described per policy. Not runtime PBR, motion/collision certification or measured performance.'}
    for level in plan['levels']:
        role = level['role']
        inputs = []
        files = {}
        for name, asset in asset_rows.items():
            if name in level.get('files', {}):
                entry = level['files'][name]
                path = local(entry['path'])
                expected = entry['sha256']
            else:
                row = refined['assets'][name + '/' + role]
                path = baseline / row['output']
                expected = row['sha256']
            if digest(path) != expected:
                raise ValueError('trial input hash mismatch: ' + str(path))
            doc, _ = read_glb(path)
            copies = max(1, len(asset['placements_in_source_arena_frame']))
            stored_meshes = {doc['nodes'][i]['mesh'] for i, _, _ in scene_nodes(doc) if 'mesh' in doc['nodes'][i]}
            stored = sum(doc['accessors'][p.get('indices', p['attributes']['POSITION'])]['count'] // 3
                         for mi in stored_meshes for p in doc['meshes'][mi]['primitives'])
            files[name] = {'path': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                           'sha256': expected, 'triangles': scene_triangles(doc) * copies,
                           'stored_triangles': stored, 'bytes': path.stat().st_size}
            inputs.append((name, path, asset['placements_in_source_arena_frame']))
        paths[level['id']] = inputs
        report['levels'].append({**{k: v for k, v in level.items() if k != 'files'}, 'files': files,
                                 'triangles': sum(r['triangles'] for r in files.values()),
                                 'stored_triangles': sum(r['stored_triangles'] for r in files.values()),
                                 'bytes': sum(r['bytes'] for r in files.values())})
    reference, reference_owners = render.load_stage(reference_inputs)
    data, owners = {}, {}
    for stage, inputs in paths.items():
        data[stage], owners[stage] = render.load_stage(inputs)
        row = next(r for r in report['levels'] if r['id'] == stage)
        if len(data[stage][0]) != row['triangles']:
            raise ValueError('rendered triangles differ from count')
    cache = {}
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        helper = tmp / 'raster'
        subprocess.run([shutil.which('clang++') or shutil.which('g++'), '-O3', '-std=c++17',
                        str(ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'), '-o', str(helper)], check=True)
        for group in ('field', 'tech-core', 'rune', 'dart-station', 'outpost', 'base', 'resource-area', 'energy-unit'):
            anchor = None
            if group in ('dart-station', 'resource-area', 'energy-unit'):
                first = next(v for v in reference_owners.values() if v['component_id'].startswith(group + '/'))
                g = reference[0][reference[4] == first['index']]
                anchor = (g.min((0, 1)) + g.max((0, 1))) / 2
            camera = render.select_group(reference, reference_owners, group, anchor)[0]
            selected = {s: render.select_group(d, owners[s], group, anchor) for s, d in data.items()}
            folder = out / 'renders' / group
            folder.mkdir(parents=True, exist_ok=True)
            views = [('oblique', (1, 1.2 if group == 'field' else .5, 1)),
                     ('reverse', (-1, 1.2 if group == 'field' else .5, -1)),
                     ('top', (0, 1, .000001)), ('front', (0, .000001, 1)),
                     ('back', (0, .000001, -1)), ('side', (1, .000001, 0)),
                     ('bottom', (0, -1, .000001))]
            for stage, d in selected.items():
                content = hashlib.sha256()
                for array in (*d[:4], d[5]):
                    content.update(np.ascontiguousarray(array).tobytes())
                for view_name, direction in views:
                    key = (group, view_name, content.hexdigest())
                    target = cache.get(key)
                    if target is None:
                        target = folder / (stage + '-' + view_name + '.webp')
                        image = raster(d, camera, direction, helper, tmp, tmp / 'frame.png')
                        Image.fromarray(image).save(target, lossless=True)
                        cache[key] = target
                    report['views'].append({'group': group, 'view': view_name, 'stage': stage,
                                            'triangles': len(d[0]), 'image': str(target.relative_to(out))})
            print('rendered feature trials', group, flush=True)
    for level in report['levels']:
        for row in level['files'].values():
            if digest(local(row['path'])) != row['sha256']:
                raise ValueError('trial changed during render')
    report['unique_images'] = len(cache)
    report['producer_sha256'] = digest(Path(__file__))
    (out / 'review.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
