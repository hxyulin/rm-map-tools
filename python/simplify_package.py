#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Simplify a bound CAD package without changing semantic nodes or surfaces.

ocpenv/bin/python python/simplify_package.py rules/simplify-simulation.example.json
Requires meshoptimizer==0.2.30a0. Uses indexed edge collapses, configurable open
borders, and exact position welding. Error values are meshoptimizer's metric, not a
certified Hausdorff distance to the STEP. No components or faces are size-filtered.
"""
import argparse
import copy
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np
import meshoptimizer as mo
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from gltf_scene import accessor, read_glb, write_glb, scene_nodes
from mesh_quality import deviation

METHOD = 'meshopt-simplification-v1'
BOUNDARY_METHOD = 'meshopt-boundary-simplification-v1'
PROTECTED_ROLES = {'led_surface', 'rune_target', 'dart_detector', 'guiding_light'}
PROTECTED_LAYERS = {'markings', 'lights'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, value):
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('package path escapes root')
    return path


def protected(metadata):
    return bool(set(metadata.get('roles', [])) & PROTECTED_ROLES or metadata.get('layer') in PROTECTED_LAYERS)


def simplify_mesh(points, triangles, error_m, lock_borders=True):
    """Weld identical positions, then collapse edges with the requested border policy."""
    if type(lock_borders) is not bool:
        raise ValueError('lock_borders must be boolean')
    points, triangles = np.asarray(points, dtype=np.float32), np.asarray(triangles)
    if points.ndim != 2 or points.shape[1] != 3 or triangles.ndim != 2 or triangles.shape[1] != 3 or not np.issubdtype(triangles.dtype, np.integer):
        raise ValueError('expected Nx3 positions and integer Mx3 triangles')
    if not math.isfinite(error_m) or error_m <= 0:
        raise ValueError('expected finite positive mesh error')
    if not np.isfinite(points).all() or not len(triangles) or triangles.min() < 0 or triangles.max() >= len(points):
        raise ValueError('invalid triangle mesh')
    points, inverse = np.unique(np.asarray(points, dtype=np.float32), axis=0, return_inverse=True)
    indices = np.ascontiguousarray(inverse[triangles.ravel()], dtype=np.uint32)
    points = np.ascontiguousarray(points)
    result = np.empty_like(indices)
    error = np.zeros(1, np.float32)
    options = mo.SIMPLIFY_ERROR_ABSOLUTE | (mo.SIMPLIFY_LOCK_BORDER if lock_borders else 0)
    count = mo.simplify(result, indices, points, target_index_count=3,
                        target_error=error_m, options=options,
                        result_error=error)
    if count % 3 or count > len(indices) or not np.isfinite(error[0]) or error[0] > error_m + 1e-7:
        raise ValueError(f'invalid simplifier result: count={count}, input={len(indices)}, error={error[0]}, limit={error_m}')
    triangles = result[:count].reshape(-1, 3)
    # Never let a closed or degenerate disconnected detail disappear entirely.
    source = indices.reshape(-1, 3)
    rows = np.repeat(source[:, 0], 2)
    cols = source[:, 1:].ravel()
    graph = coo_matrix((np.ones(len(rows), dtype=np.uint8), (rows, cols)), shape=(len(points), len(points))).tocsr()
    _, labels = connected_components(graph, directed=False)
    missing = ~np.isin(labels[source[:, 0]], labels[triangles.ravel()])
    if missing.any():
        triangles = np.vstack([triangles, source[missing]])
    used, inverse = np.unique(triangles, return_inverse=True)
    return points[used], inverse.reshape(-1, 3), float(error[0])


def append_accessor(doc, binary, values, kind, component):
    binary.extend(b'\0' * (-len(binary) % 4))
    offset = len(binary)
    binary.extend(values.tobytes())
    view = len(doc['bufferViews'])
    doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': values.nbytes})
    a = {'bufferView': view, 'componentType': component, 'count': len(values), 'type': kind}
    if kind == 'VEC3':
        a.update(min=values.min(axis=0).tolist(), max=values.max(axis=0).tolist())
    doc['accessors'].append(a)
    return len(doc['accessors']) - 1


def compact(doc, binary):
    """Drop orphan meshes/accessors and repack rigid GLB data; keep node indices."""
    used_meshes = sorted({n['mesh'] for n in doc['nodes'] if 'mesh' in n})
    mesh_map = {old: new for new, old in enumerate(used_meshes)}
    doc['meshes'] = [doc['meshes'][i] for i in used_meshes]
    for node in doc['nodes']:
        if 'mesh' in node:
            node['mesh'] = mesh_map[node['mesh']]
    slots = []
    for mesh in doc['meshes']:
        for p in mesh['primitives']:
            slots += [(p['attributes'], k) for k in p['attributes']]
            if 'indices' in p:
                slots.append((p, 'indices'))
    used = sorted({obj[key] for obj, key in slots})
    remap = {old: new for new, old in enumerate(used)}
    new_accessors, views, output = [], [], bytearray()
    for i in used:
        a = copy.deepcopy(doc['accessors'][i])
        data = np.ascontiguousarray(accessor(doc, binary, i)).tobytes()
        output.extend(b'\0' * (-len(output) % 4))
        views.append({'buffer': 0, 'byteOffset': len(output), 'byteLength': len(data)})
        output.extend(data)
        a.pop('byteOffset', None)
        a['bufferView'] = len(views) - 1
        new_accessors.append(a)
    for obj, key in slots:
        obj[key] = remap[obj[key]]
    # Embedded texture payloads are independent of the mesh accessors.
    for image in doc.get('images', []):
        if 'bufferView' in image:
            view = doc['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            data = binary[start:start + view['byteLength']]
            output.extend(b'\0' * (-len(output) % 4))
            image['bufferView'] = len(views)
            views.append({'buffer': 0, 'byteOffset': len(output), 'byteLength': len(data)})
            output.extend(data)
    doc['accessors'], doc['bufferViews'] = new_accessors, views
    doc['buffers'] = [{'byteLength': len(output)}]
    return bytes(output)


def scene_triangles(doc):
    return sum(sum(doc['accessors'][p.get('indices', p['attributes']['POSITION'])]['count'] // 3
                   for p in doc['meshes'][doc['nodes'][i]['mesh']]['primitives'])
               for i, _, _ in scene_nodes(doc) if 'mesh' in doc['nodes'][i])


def check_bindings(doc, binding):
    if binding is None:
        return
    for node in binding.get('nodes', []):
        if doc['nodes'][node['node']].get('extras', {}).get('rm') != node['metadata']:
            raise ValueError('semantic node binding mismatch')
    for surface in binding.get('surfaces', []):
        if surface.get('primitive') is not None:
            node = doc['nodes'][surface['node']]
            p = doc['meshes'][node['mesh']]['primitives'][surface['primitive']]
            if p.get('extras', {}).get('rm') != surface['metadata']:
                raise ValueError('semantic surface binding mismatch')


def simplify_glb(path, error_mm, binding=None, sampled_limit_mm=None, deviation_samples=None, lock_borders=True, preserve=()):
    if type(lock_borders) is not bool:
        raise ValueError('lock_borders must be boolean')
    if deviation_samples is None:
        deviation_samples = 96 if lock_borders else 1024
    if type(deviation_samples) is not int or not 96 <= deviation_samples <= 16384:
        raise ValueError('deviation_samples must be an integer from 96 to 16384')
    if not lock_borders and deviation_samples < 1024:
        raise ValueError('unlocked boundaries require at least 1024 deviation samples per direction')
    sampled_limit_mm = error_mm * 4 if sampled_limit_mm is None else sampled_limit_mm
    doc, binary = read_glb(path)
    original_nodes = copy.deepcopy(doc['nodes'])
    if doc.get('skins') or doc.get('animations') or doc.get('extensionsUsed') or any('weights' in n or 'skin' in n for n in doc['nodes']):
        raise ValueError('simplification currently supports rigid GLBs without extensions')
    for mesh in doc['meshes']:
        if any(p.get('mode', 4) != 4 or p.get('targets') or p.get('extensions') for p in mesh['primitives']):
            raise ValueError('expected rigid triangle primitives')
    check_bindings(doc, binding)
    before = scene_triangles(doc)
    old_bytes = path.stat().st_size
    preserved = set()
    live_nodes = [doc['nodes'][i] for i, _, _ in scene_nodes(doc)]
    for selector in preserve:
        matches = [node for node in live_nodes if node.get('name') == selector['node']]
        if len(matches) != 1 or 'mesh' not in matches[0]:
            raise ValueError(f'preserve selector must identify one live mesh node: {selector}')
        mi, pi = matches[0]['mesh'], selector['primitive']
        if not 0 <= pi < len(doc['meshes'][mi]['primitives']):
            raise ValueError(f'preserve primitive does not exist: {selector}')
        preserved.add((mi, pi))
    # Sharing a mesh with a protected node protects every use of that mesh.
    protected_meshes, scales = set(), {}
    inherited = {}
    for i, world, parent in scene_nodes(doc):
        node = doc['nodes'][i]
        inherited[i] = protected(node.get('extras', {}).get('rm', {})) or inherited.get(parent, False)
        if 'mesh' in node:
            mi = node['mesh']
            scales[mi] = max(scales.get(mi, 0), float(np.linalg.svd(world[:3, :3], compute_uv=False).max()))
            if inherited[i]:
                protected_meshes.add(mi)
    data = bytearray(binary)
    details = []
    for mi, mesh in enumerate(doc['meshes']):
        if mi not in scales:
            continue
        for pi, p in enumerate(mesh['primitives']):
            before_count = doc['accessors'][p.get('indices', p['attributes']['POSITION'])]['count'] // 3
            reason = None
            if (mi, pi) in preserved:
                reason = 'explicit_preservation'
            elif mi in protected_meshes or protected(p.get('extras', {}).get('rm', {})):
                reason = 'protected_semantics'
            elif set(p['attributes']) - {'POSITION', 'NORMAL'}:
                reason = 'additional_vertex_attributes'
            elif before_count < 8:
                reason = 'already_small'
            if reason:
                details.append({'mesh': mi, 'primitive': pi, 'before': before_count, 'after': before_count, 'kept': reason})
                continue
            points = accessor(doc, data, p['attributes']['POSITION']).copy()
            indices = accessor(doc, data, p['indices']).copy() if 'indices' in p else np.arange(len(points))
            scale = scales[mi]
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError('invalid mesh instance scale')
            original_points, original_triangles = points, indices.reshape(-1, 3)
            best = None
            refinement_factor = 4 if lock_borders else 2
            for attempt in range(4 if lock_borders else 6):
                points, triangles, error = simplify_mesh(original_points, original_triangles,
                                                        error_mm / 1000 / scale / refinement_factor ** attempt, lock_borders)
                if best is not None and len(triangles) >= len(best[1]):
                    continue
                quality = deviation(original_points, original_triangles, points, triangles, count=deviation_samples)
                if quality['max'] * scale * 1000 <= sampled_limit_mm:
                    best = (points, triangles, error, quality, attempt)
                    if lock_borders:
                        break
            if best is None:
                details.append({'mesh': mi, 'primitive': pi, 'before': before_count, 'after': before_count,
                                'kept': 'sampled_deviation_limit'})
                continue
            points, triangles, error, quality, attempt = best
            # Flat normals match this exporter's existing shading and retain creases.
            flat = np.ascontiguousarray(points[triangles.ravel()], dtype='<f4')
            normals = np.cross(flat[1::3] - flat[0::3], flat[2::3] - flat[0::3])
            lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            # Retained degenerate components still require valid glTF normals.
            normals = np.where(lengths > 1e-30, normals / np.maximum(lengths, 1e-30), [0.0, 0.0, 1.0])
            normals = np.ascontiguousarray(np.repeat(normals, 3, axis=0), dtype='<f4')
            p['attributes'] = {'POSITION': append_accessor(doc, data, flat, 'VEC3', 5126),
                               'NORMAL': append_accessor(doc, data, normals, 'VEC3', 5126)}
            p['indices'] = append_accessor(doc, data, np.arange(len(flat), dtype='<u4'), 'SCALAR', 5125)
            details.append({'mesh': mi, 'primitive': pi, 'before': before_count, 'after': len(triangles),
                            'estimated_error_mm': error * scale * 1000, 'refinements': attempt,
                            'sample_count': quality['sample_count'], 'max_sampled_deviation_mm': quality['max'] * scale * 1000})
    binary = compact(doc, data)
    # Only node mesh references may change during compaction.
    for old, new in zip(original_nodes, doc['nodes']):
        if {k: v for k, v in old.items() if k != 'mesh'} != {k: v for k, v in new.items() if k != 'mesh'}:
            raise ValueError('node hierarchy or metadata changed')
    check_bindings(doc, binding)
    record = {'method': METHOD if lock_borders else BOUNDARY_METHOD,
              'error_limit_mm': error_mm, 'deviation_triangles_per_direction': deviation_samples,
              'refinement_factor': 4 if lock_borders else 2,
              'preserved_primitives': list(preserve),
              'estimated_error_mm': max((p.get('estimated_error_mm', 0) for p in details), default=0),
              'sampled_deviation_limit_mm': sampled_limit_mm,
              'max_sampled_deviation_mm': max((p.get('max_sampled_deviation_mm', 0) for p in details), default=0),
              'visual_semantics_protected': True, 'open_borders_locked': lock_borders, 'position_welding': 'exact',
              'before_triangles': before, 'after_triangles': scene_triangles(doc),
              'before_bytes': old_bytes, 'primitives': details}
    doc.setdefault('asset', {}).setdefault('extras', {})['mesh_simplification'] = {k: v for k, v in record.items() if k != 'primitives'}
    write_glb(path, doc, binary)
    record['after_bytes'] = path.stat().st_size
    return record


def read_config(path):
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or set(config) - {'schema_version', 'input', 'output', 'defaults', 'assets'} or type(config.get('schema_version')) is not int or config['schema_version'] != 1:
        raise ValueError('expected simplification schema_version 1 with known fields')
    for key in ('input', 'output'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f'{key}: expected path')
        config[key] = (path.parent / config[key]).resolve()
    if config['output'].exists() or config['output'].is_relative_to(config['input']):
        raise ValueError('output must be new and outside input package')
    if not isinstance(config.get('defaults'), dict) or not isinstance(config.get('assets', {}), dict):
        raise ValueError('expected defaults and optional assets mappings')
    for block in [config['defaults'], *config.get('assets', {}).values()]:
        if not isinstance(block, dict) or set(block) - {'visual_error_mm', 'collision_error_mm', 'visual_sampled_limit_mm', 'collision_sampled_limit_mm', 'deviation_samples', 'enabled', 'visual_lock_borders', 'collision_lock_borders', 'visual_preserve', 'collision_preserve'}:
            raise ValueError('unknown simplification setting')
        for key, value in block.items():
            if key in {'visual_preserve', 'collision_preserve'}:
                if not isinstance(value, list) or any(not isinstance(s, dict) or set(s) != {'node', 'primitive'}
                        or not isinstance(s['node'], str) or not s['node'] or type(s['primitive']) is not int
                        or s['primitive'] < 0 for s in value):
                    raise ValueError(f'{key} requires node-name and primitive-index selectors')
            elif key in {'enabled', 'visual_lock_borders', 'collision_lock_borders'}:
                if not isinstance(value, bool): raise ValueError(f'{key} must be boolean')
            elif key == 'deviation_samples':
                if type(value) is not int or not 96 <= value <= 16384:
                    raise ValueError('deviation_samples must be an integer from 96 to 16384')
            elif isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError('error limits must be finite positive millimetres')
    if not {'visual_error_mm', 'collision_error_mm'} <= config['defaults'].keys():
        raise ValueError('both default error limits are required')
    return config


def run(config):
    if importlib.metadata.version('meshoptimizer') != '0.2.30a0':
        raise ValueError('this pipeline requires meshoptimizer==0.2.30a0')
    root, output = config['input'], config['output']
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'input': str(root), 'assets': {}}
    with tempfile.TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / 'package'
        shutil.copytree(root, stage)
        manifests = {}
        names = set()
        for scope in ('', 'equipment'):
            mp = stage / scope / 'manifest.json'
            manifest = json.loads(mp.read_text())
            if manifest.get('schema_version') != 1 or manifest.get('units') != 'metres':
                raise ValueError('expected schema 1 package in metres')
            manifests[scope] = (mp, manifest)
            names.update(manifest['assets'])
        if set(config.get('assets', {})) - names:
            raise ValueError('unknown asset override')
        for scope, (mp, manifest) in manifests.items():
            base = mp.parent
            descriptor = manifest.get('articulation')
            sidecar = None
            if descriptor:
                sp = safe_path(base, descriptor['file'])
                if digest(sp) != descriptor['sha256']: raise ValueError('sidecar checksum mismatch')
                sidecar = json.loads(sp.read_text())
            for name, entry in manifest['assets'].items():
                settings = {**config['defaults'], **config.get('assets', {}).get(name, {})}
                if settings.get('enabled', True) and entry.get('mesh_simplification'):
                    raise ValueError('use an unsimplified input package; repeated simplification would accumulate error')
                if settings.get('enabled', True) and ('collision' not in entry or entry['visual'] == entry['collision']):
                    raise ValueError('simplification requires separate visual and collision files')
                result = {}
                start = time.perf_counter()
                for kind in ('visual', 'collision'):
                    if kind not in entry: continue
                    path = safe_path(base, entry[kind])
                    old_hash = digest(path)
                    if old_hash != entry.get(kind + '_sha256'): raise ValueError(f'{name}/{kind}: hash mismatch')
                    binding = sidecar['assets'].get(name, {}).get('files', {}).get(kind) if sidecar else None
                    if binding and (binding['sha256'] != old_hash or binding['file'] != entry[kind]):
                        raise ValueError('sidecar/manifest file mismatch')
                    if not settings.get('enabled', True): continue
                    result[kind] = simplify_glb(path, settings[kind + '_error_mm'], binding,
                                                settings.get(kind + '_sampled_limit_mm'), settings.get('deviation_samples'),
                                                settings.get(kind + '_lock_borders', True), settings.get(kind + '_preserve', ()))
                    result[kind]['input_sha256'] = old_hash
                    entry[kind + '_sha256'] = digest(path)
                    entry['triangles' if kind == 'visual' else 'collision_triangles'] = result[kind]['after_triangles']
                    if binding: binding['sha256'] = entry[kind + '_sha256']
                if result:
                    entry['mesh_simplification'] = {kind: {k: v for k, v in r.items() if k != 'primitives'} for kind, r in result.items()}
                    entry['collision_method'] = result['collision']['method']
                    report['assets'][scope + '/' + name] = result
                    counts = ', '.join(f"{k} {r['before_triangles']:,}->{r['after_triangles']:,}" for k, r in result.items())
                    print(f'{name}: {counts}; {time.perf_counter() - start:.2f}s', flush=True)
            if sidecar:
                sp.write_text(json.dumps(sidecar, indent=2, allow_nan=False) + '\n')
                descriptor['sha256'] = digest(sp)
            manifest['collision_contract'] = 'Per-asset source tessellation or checked mesh simplification, with exact position welding and independent error and boundary settings. See each asset record for locked or simplified borders. No hulls, voxels or size-based face deletion.'
            manifest['mesh_simplification'] = {'settings': {k: v for k, v in config.items() if k not in ('input', 'output')}}
            manifest.pop('reference_equipment', None)
            mp.write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
        (stage / 'mesh-simplification.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        stage.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    try:
        run(read_config(args.config.resolve()))
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__': main()
