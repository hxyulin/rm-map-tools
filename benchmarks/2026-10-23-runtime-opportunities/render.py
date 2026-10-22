# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Export the exact opportunity probes and render matched inspection views."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import meshoptimizer as mo
import numpy as np
from PIL import Image
from cad_experimental_lod import export_trial
from gltf_scene import accessor, local_matrix, read_glb, scene_nodes, write_glb
from simplify_package import scene_triangles


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def export_probe(source, target, metric, audit):
    doc, _ = read_glb(source)
    scales = {}
    for i, world, _ in scene_nodes(doc):
        if 'mesh' in doc['nodes'][i]:
            mi = doc['nodes'][i]['mesh']
            scales[mi] = max(scales.get(mi, 0), np.linalg.svd(world[:3, :3], compute_uv=False).max())
    records = iter(audit['primitives'])

    def select(p, t, material, primitive):
        row = next(records)
        q, first, inv = np.unique(p, axis=0, return_index=True, return_inverse=True)
        q = np.ascontiguousarray((q.astype(float) - q.astype(float).mean(0)) * scales[row['mesh']], dtype=np.float32)
        ix = np.ascontiguousarray(inv[t].ravel(), dtype=np.uint32)
        dest = np.empty_like(ix)
        count = mo.simplify(dest, ix, q, target_index_count=3,
                            target_error=metric / 1000, options=mo.SIMPLIFY_ERROR_ABSOLUTE)
        result = first[dest[:count]].reshape(-1, 3) if count else t.copy()
        if len(result) != row['probes'][str(metric)]['triangles']:
            raise ValueError('export probe differs from audit')
        return result, {'probe_metric_mm': metric}

    target.parent.mkdir(parents=True, exist_ok=True)
    result = export_trial(source, target, 1, index_selector=select, align_normals=True)
    if next(records, None) is not None:
        raise ValueError('unvisited audit primitive')
    doc, blob = read_glb(target)
    for item in [doc['asset'], *[p for mesh in doc['meshes'] for p in mesh['primitives']]]:
        extras = item.setdefault('extras', {})
        extras.pop('visual_lod_target_ratio', None)
        extras['probe_metric_mm'] = metric
    write_glb(target, doc, blob)
    if scene_triangles(read_glb(target)[0]) * audit['placements'] != audit['probe_placed_triangles'][str(metric)]:
        raise ValueError('written scene differs from placed audit total')
    result.pop('primitives')
    result.pop('target_ratio')
    return {**result, 'sha256': digest(target), 'metric_mm': metric}


def load_stage(inputs):
    geometry, colors, uvs, flags, labels = [], [], [], [], []
    owners = {}
    texture = np.zeros((1, 1, 3), np.uint8)
    texture_hash = None
    # Runtime source coordinates are Z up. Diagnostics use Y up.
    frame = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    for name, path, placements in inputs:
        doc, blob = read_glb(path)
        for copy, placement in enumerate(placements or [{}]):
            external = local_matrix({'translation': placement.get('translation_m', [0, 0, 0]),
                                     'rotation': placement.get('rotation_xyzw', [0, 0, 0, 1])})
            inherited = {}
            for index, world, parent in scene_nodes(doc):
                node = doc['nodes'][index]
                component = node.get('extras', {}).get('component_id')
                inherited[index] = (component, index) if component else inherited.get(parent, (name, -1))
                if 'mesh' not in node:
                    continue
                component, owner_node = inherited[index]
                key = (name, copy, owner_node)
                if key not in owners:
                    owners[key] = {'index': len(owners), 'component_id': component, 'asset': name, 'copy': copy}
                owner = owners[key]['index']
                matrix = external @ world
                for prim in doc['meshes'][node['mesh']]['primitives']:
                    p = accessor(doc, blob, prim['attributes']['POSITION']).astype(float)
                    t = accessor(doc, blob, prim['indices']).reshape(-1, 3)
                    if np.linalg.det(matrix[:3, :3]) < 0:
                        t = t[:, ::-1]
                    geometry.append(((p @ matrix[:3, :3].T + matrix[:3, 3]) @ frame.T)[t])
                    mat = doc['materials'][prim['material']]
                    pbr = mat.get('pbrMetallicRoughness', {})
                    textured = 'baseColorTexture' in pbr
                    if textured:
                        image = doc['images'][doc['textures'][pbr['baseColorTexture']['index']]['source']]
                        view = doc['bufferViews'][image['bufferView']]
                        raw = blob[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']]
                        h = hashlib.sha256(raw).hexdigest()
                        if texture_hash is not None and h != texture_hash:
                            raise ValueError('diagnostic renderer supports one unique base texture')
                        texture_hash = h
                        texture = np.asarray(Image.open(io.BytesIO(raw)).convert('RGB')).copy()
                        uvs.append(accessor(doc, blob, prim['attributes']['TEXCOORD_0'])[t])
                        color = [1, 1, 1]
                    else:
                        uvs.append(np.zeros((len(t), 3, 2)))
                        color = mat.get('extras', {}).get('step_colour_srgb')
                        if color is None:
                            linear = np.array(pbr.get('baseColorFactor', [.35, .35, .35, 1])[:3])
                            color = np.where(linear <= .0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - .055)
                    colors.extend([color] * len(t))
                    flags.extend([int(textured)] * len(t))
                    labels.extend([owner] * len(t))
    return (np.concatenate(geometry), np.array(colors), np.concatenate(uvs),
            np.array(flags, np.int32), np.array(labels), texture), owners


def select_group(data, owners, group, anchor=None):
    if group == 'field':
        return data
    if group in ('base', 'outpost', 'rune', 'tech-core'):
        selected = [v['index'] for v in owners.values() if v['asset'] == group and v['copy'] == 0]
    else:
        candidates = {}
        for v in owners.values():
            component = v['component_id']
            if component.startswith(group + '/') or (group == 'dart-station' and component.startswith('dart-station-')):
                g = data[0][data[4] == v['index']]
                centre = (g.min((0, 1)) + g.max((0, 1))) / 2
                candidates.setdefault(component, []).append((np.linalg.norm(centre - anchor), v['index']))
        selected = [min(v)[1] for v in candidates.values()]
    mask = np.isin(data[4], selected)
    if not mask.any():
        raise ValueError('empty subject: ' + group)
    return tuple(v[mask] for v in data[:5]) + (data[5],)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT.parent / 'rm-simulator/field-2027')
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-runtime-opportunities')
    args = parser.parse_args()
    out = args.out.resolve()
    audit = json.loads((out / 'audit.json').read_text())
    sources = []
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = args.package / relative
        if digest(manifest) != audit['manifests'][relative]:
            raise ValueError('manifest differs from audited input')
        for name, asset in json.loads(manifest.read_text())['assets'].items():
            sources.append((name, manifest.parent, asset))
    paths = {}
    report = {'stages': {}, 'views': [], 'scope': 'Inspection-only exports of exact audited index probes. Matched source-color and embedded-texture flat two-sided orthographic diagnostics, not runtime PBR or collision validation.'}
    for role in ('visual', 'collision'):
        for metric in (None, .1, 1, 4):
            stage = role + ('-current' if metric is None else '-' + str(metric) + 'mm')
            inputs = []
            for name, parent, asset in sources:
                source = parent / asset[role]
                source_audit = audit['assets'][name + '/' + role]
                if digest(source) != source_audit['sha256']:
                    raise ValueError('source differs from audit')
                target = source if metric is None else out / 'meshes' / stage / asset[role]
                if metric is not None:
                    export_probe(source, target, metric, source_audit)
                inputs.append((name, target, asset['placements_in_source_arena_frame']))
            paths[stage] = inputs
            report['stages'][stage] = {'triangles': sum(scene_triangles(read_glb(p)[0]) * max(1, len(placements)) for _, p, placements in inputs),
                                       'files': {str(p.resolve()): digest(p) for _, p, _ in inputs}}
            print('exported', stage, report['stages'][stage]['triangles'], flush=True)
    raster = module('texture_raster', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
    data = {}
    owners = {}
    for stage, inputs in paths.items():
        data[stage], owners[stage] = load_stage(inputs)
        if len(data[stage][0]) != report['stages'][stage]['triangles']:
            raise ValueError('rendered geometry count differs from export')
    groups = ('field', 'tech-core', 'rune', 'dart-station', 'outpost', 'base', 'resource-area', 'energy-unit')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        helper = tmp / 'raster'
        subprocess.run([shutil.which('clang++') or shutil.which('g++'), '-O3', '-std=c++17',
                        str(ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'), '-o', str(helper)], check=True)
        for group in groups:
            anchor = None
            if group in ('dart-station', 'resource-area', 'energy-unit'):
                first = next(v for v in owners['visual-current'].values() if v['component_id'].startswith(group + '/'))
                g = data['visual-current'][0][data['visual-current'][4] == first['index']]
                anchor = (g.min((0, 1)) + g.max((0, 1))) / 2
            selected = {s: select_group(d, owners[s], group, anchor) for s, d in data.items()}
            folder = out / 'renders' / group
            folder.mkdir(parents=True, exist_ok=True)
            views = [('oblique', (1, 1.2 if group == 'field' else .5, 1)),
                     ('reverse', (-1, 1.2 if group == 'field' else .5, -1)),
                     ('top', (0, 1, .000001)), ('front', (0, .000001, 1)),
                     ('back', (0, .000001, -1)), ('side', (1, .000001, 0)),
                     ('bottom', (0, -1, .000001))]
            for view_name, direction in views:
                for stage, d in selected.items():
                    img = raster(d, selected['visual-current'][0], direction, helper, tmp, tmp / 'frame.png')
                    target = folder / (stage + '-' + view_name + '.webp')
                    Image.fromarray(img).save(target, lossless=True)
                    report['views'].append({'group': group, 'view': view_name, 'stage': stage,
                                            'triangles': len(d[0]), 'image': str(target.relative_to(out))})
            print('rendered', group, flush=True)
    for name, parent, asset in sources:
        for role in ('visual', 'collision'):
            if digest(parent / asset[role]) != audit['assets'][name + '/' + role]['sha256']:
                raise ValueError('input changed during export/render')
    report['producer_sha256'] = digest(Path(__file__))
    (out / 'renders.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
