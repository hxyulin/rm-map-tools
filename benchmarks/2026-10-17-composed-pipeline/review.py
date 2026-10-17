#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render actual complete GLBs and isolated equipment in their source poses."""
import argparse, collections, importlib.util, io, json, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image
from gltf_scene import read_glb, accessor, scene_nodes
from plan_cad_lods import digest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


def load_scene(path):
    doc, blob = read_glb(path); geometry, colors, uvs, flags, owners = [], [], [], [], []
    texture = np.zeros((1, 1, 3), np.uint8); occurrences = {}; texture_image = None
    for index, world, parent in scene_nodes(doc):
        node = doc['nodes'][index]
        if 'mesh' not in node: continue
        occurrence = node['extras']['composition_occurrence']; key = occurrence['node_id']
        if key not in occurrences: occurrences[key] = {'index': len(occurrences), 'component_id': occurrence['component_id']}
        owner = occurrences[key]['index']
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            t = accessor(doc, blob, primitive['indices']).reshape(-1, 3)
            if np.linalg.det(world[:3, :3]) < 0: t = t[:, ::-1]
            p = accessor(doc, blob, primitive['attributes']['POSITION']).astype(float)
            g = (p @ world[:3, :3].T + world[:3, 3])[t]; geometry.append(g)
            material = doc['materials'][primitive['material']]; pbr = material['pbrMetallicRoughness']
            textured = 'baseColorTexture' in pbr
            if textured:
                image_index = doc['textures'][pbr['baseColorTexture']['index']]['source']
                if texture_image is not None and texture_image != image_index: raise ValueError('review supports one embedded image')
                texture_image = image_index; image = doc['images'][image_index]; view = doc['bufferViews'][image['bufferView']]
                texture = np.asarray(Image.open(io.BytesIO(blob[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']])).convert('RGB')).copy()
                uvs.append(accessor(doc, blob, primitive['attributes']['TEXCOORD_0'])[t]); colors.extend([[1, 1, 1]] * len(t))
            else:
                uvs.append(np.zeros((len(t), 3, 2))); colors.extend([material.get('extras', {}).get('step_colour_srgb') or [.6275] * 3] * len(t))
            flags.extend([int(textured)] * len(t)); owners.extend([owner] * len(t))
    data = (np.concatenate(geometry), np.array(colors), np.concatenate(uvs), np.array(flags, np.int32), np.array(owners), texture)
    return data, occurrences


def select(data, occurrences, group, anchor):
    candidates = {v['component_id']: [] for v in occurrences.values() if v['component_id'].split('/')[0] == group}
    if group == 'dart-station': candidates.update({v['component_id']: [] for v in occurrences.values() if v['component_id'].startswith('dart-station-')})
    for key, value in occurrences.items():
        if value['component_id'] in candidates:
            g = data[0][data[4] == value['index']]; centre = (g.min((0, 1)) + g.max((0, 1))) / 2
            candidates[value['component_id']].append((np.linalg.norm(centre - anchor), value['index']))
    selected = [min(values)[1] for values in candidates.values()]
    mask = np.isin(data[4], selected)
    return tuple(value[mask] for value in data[:5]) + (data[5],)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); a = ap.parse_args(); out = a.out.resolve()
    report_path = out / 'assembly.json'; report = json.loads(report_path.read_bytes())
    for row in report['stages']:
        if digest(out / (row['stage'] + '-field.glb')) != row['glb_sha256']: raise ValueError('assembled GLB changed')
    data = {}; owners = {}
    for stage in ['reference', 'candidate']: data[stage], owners[stage] = load_scene(out / (stage + '-field.glb'))
    raster = module('raster', ROOT / 'benchmarks/2026-10-17-base-panel-textures/review.py')
    metrics = module('metrics', ROOT / 'benchmarks/2026-10-17-base-housing-aggressive/review.py')
    results = []
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'
        subprocess.run([shutil.which('clang++'), '-O3', '-std=c++17', str(ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'), '-o', str(helper)], check=True)
        groups = ['field', 'outpost', 'rune', 'technology-core', 'resource-area', 'dart-station', 'energy-unit']
        for group in groups:
            if group == 'field': selected = data
            else:
                first = next(v for v in owners['reference'].values() if v['component_id'].startswith(group + '/'))
                g = data['reference'][0][data['reference'][4] == first['index']]; anchor = (g.min((0, 1)) + g.max((0, 1))) / 2
                selected = {s: select(d, owners[s], group, anchor) for s, d in data.items()}
            folder = out / 'review' / group; folder.mkdir(parents=True, exist_ok=True)
            views = [('oblique', (1, 1.2 if group == 'field' else .5, 1)), ('reverse', (-1, 1.2 if group == 'field' else .5, -1)), ('top', (0, 1, .000001))]
            if group != 'field': views += [('front', (0, .000001, 1)), ('back', (0, .000001, -1)), ('bottom', (0, -1, .000001))]
            checks = []
            for name, view in views:
                images = {stage: raster.raster(d, selected['reference'][0], view, helper, tmp, folder / (stage + '-' + name + '.png')) for stage, d in selected.items()}
                checks.append({'view': name, **metrics.metric(images['reference'], images['candidate'])})
                sheet = Image.new('RGB', (1200, 600))
                for i, stage in enumerate(['reference', 'candidate']): sheet.paste(Image.fromarray(images[stage]).resize((600, 600), Image.Resampling.LANCZOS), (i * 600, 0))
                sheet.save(folder / (name + '.webp'), lossless=True, method=4)
            results.append({'group': group, 'views': checks, 'reference_triangles': len(selected['reference'][0]), 'candidate_triangles': len(selected['candidate'][0]), 'maximum_foreground_difference': max(c['foreground_difference_relative_fraction'] for c in checks)})
            print(group, results[-1]['reference_triangles'], '->', results[-1]['candidate_triangles'], 'max foreground', results[-1]['maximum_foreground_difference'], flush=True)
    result = {'assembly_sha256': digest(report_path), 'groups': results, 'producer_sha256': {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), ROOT / 'benchmarks/2026-10-17-base-panel-textures/review.py', ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp']}, 'scope': 'Actual assembled GLBs at original source occurrences. Complete field and nearest complete equipment instances, matched 1200px source-color/embedded-texture renders. Not PBR, animation or collision validation.'}
    (out / 'review.json').write_text(json.dumps(result, indent=2) + '\n')

if __name__ == '__main__': main()
