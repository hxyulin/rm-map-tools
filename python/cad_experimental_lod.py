# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Unbounded visual-only LOD trials; never suitable as certified colliders."""
import copy
import math
import numpy as np
import meshoptimizer as mo
from gltf_scene import accessor, read_glb, write_glb, scene_nodes
from simplify_package import append_accessor, compact, scene_triangles


def coarse_indices(points, triangles, ratio):
    """Cluster a primitive independently, retaining at least one source triangle.

    Returns indices into the original vertices, so selected UVs and other vertex
    attributes remain source values. This deliberately relaxes topology, openings,
    component survival and error guards. ``ratio`` is a target, not a guarantee.
    Small primitives have a floor; no material or motion scopes are combined.
    """
    p = np.asarray(points, float); t = np.asarray(triangles)
    if not math.isfinite(ratio) or not 0 < ratio <= 1:
        raise ValueError('ratio must be in (0, 1]')
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all() or t.ndim != 2 or t.shape[1] != 3 or not len(t) or not np.issubdtype(t.dtype, np.integer) or t.min() < 0 or t.max() >= len(p):
        raise ValueError('invalid triangle mesh')
    if ratio == 1 or len(t) <= 4:
        return t.copy()
    origin = (p.min(0) + p.max(0)) / 2
    positions = np.ascontiguousarray(p - origin, dtype=np.float32)
    indices = np.ascontiguousarray(t.ravel(), dtype=np.uint32)
    result = np.empty_like(indices)
    target = max(3, 3 * math.ceil(len(t) * ratio))
    while target < len(indices):
        count = mo.simplify_sloppy(result, indices, positions,
                                   target_index_count=target, target_error=1.0)
        if count % 3 or count > len(indices):
            raise ValueError('invalid simplifier index count')
        if count:
            f = result[:count].reshape(-1, 3).copy()
            if f.max() >= len(p):
                raise ValueError('invalid simplifier vertex index')
            return f
        target *= 2
    return t.copy()


def align_source_corners(points, normals, triangles):
    """Choose same-position source corners whose normals best match each face.

    Welding a hard edge for topology selection must not assign its front normal
    to a side face. This keeps source attribute values and exact positions while
    selecting an appropriate original seam corner for each output triangle.
    Call only for untextured primitives; different UV charts need their own policy.
    """
    p = np.asarray(points); n = np.asarray(normals, float); f = np.asarray(triangles)
    _, labels = np.unique(p, axis=0, return_inverse=True)
    source_order = np.argsort(labels, kind='stable')
    source_counts = np.bincount(labels); source_start = np.r_[0, np.cumsum(source_counts)]
    target_labels = labels[f.ravel()]; order = np.argsort(target_labels, kind='stable')
    counts = np.bincount(target_labels, minlength=len(source_counts)); start = np.r_[0, np.cumsum(counts)]
    g = p[f]; face = np.cross(g[:, 1] - g[:, 0], g[:, 2] - g[:, 0])
    face /= np.maximum(np.linalg.norm(face, axis=1)[:, None], 1e-30)
    normal = n / np.maximum(np.linalg.norm(n, axis=1)[:, None], 1e-30)
    result = f.ravel().copy()
    for key in np.flatnonzero((source_counts > 1) & (counts > 0)):
        corners = order[start[key]:start[key + 1]]
        candidates = source_order[source_start[key]:source_start[key + 1]]
        best = np.argmax(face[corners // 3] @ normal[candidates].T, axis=1)
        result[corners] = candidates[best]
    return result.reshape(-1, 3)


def export_trial(source, target, ratio, *, index_selector=None, align_normals=False):
    """Write a shared-mesh GLB trial with original node poses and PBR tables.

    Changes indices and compacts selected original attributes. Generated surfaces
    lose native-face identity claims. Source accessor values are not recomputed;
    original normals can consequently shade coarse faces imperfectly.
    An optional ``index_selector(points, triangles, material, primitive)`` returns
    original-vertex indices and a JSON decision record for a caller-owned policy.
    ``align_normals`` selects original hard-edge corners by output face normal on
    untextured primitives; it never computes new source attribute values.
    """
    doc, blob = read_glb(source); changed = copy.deepcopy(doc); binary = bytearray(blob)
    meshes = sorted({doc['nodes'][i]['mesh'] for i, _, _ in scene_nodes(doc)
                     if 'mesh' in doc['nodes'][i]})
    records = []; expected = {}
    for mi in meshes:
        for pi, prim in enumerate(doc['meshes'][mi]['primitives']):
            if prim.get('mode', 4) != 4 or 'targets' in prim:
                raise ValueError('only rigid triangle primitives supported')
            p = accessor(doc, blob, prim['attributes']['POSITION'])
            t = (accessor(doc, blob, prim['indices']) if 'indices' in prim
                 else np.arange(len(p))).reshape(-1, 3)
            if index_selector is None:
                f = coarse_indices(p, t, ratio); decision = {}
            else:
                f, decision = index_selector(p, t, doc['materials'][prim['material']], prim)
                f = np.asarray(f)
                if f.ndim != 2 or f.shape[1] != 3 or not len(f) or not np.issubdtype(f.dtype, np.integer) or f.min() < 0 or f.max() >= len(p):
                    raise ValueError('invalid caller-selected LOD indices')
            material = doc['materials'][prim['material']]
            textured = any('Texture' in key for key in material.get('pbrMetallicRoughness', {})) or 'normalTexture' in material
            if align_normals and not textured and 'NORMAL' in prim['attributes']:
                f = align_source_corners(p, accessor(doc, blob, prim['attributes']['NORMAL']), f)
            destination = changed['meshes'][mi]['primitives'][pi]
            used, inv = np.unique(f, return_inverse=True)
            expected[mi, pi] = (used, inv.ravel())
            for key, index in prim['attributes'].items():
                a = doc['accessors'][index]
                new = append_accessor(changed, binary, accessor(doc, blob, index)[used], a['type'], a['componentType'])
                destination['attributes'][key] = new
                if a.get('normalized'): changed['accessors'][new]['normalized'] = True
            destination['indices'] = append_accessor(changed, binary, inv.ravel().astype(np.uint32), 'SCALAR', 5125)
            destination['extras'] = {'inspection_only': True, 'derived_geometry': True,
                                     'native_identity_claim': False, 'source_mesh_index': mi,
                                     'source_primitive_index': pi, 'visual_lod_target_ratio': ratio}
            records.append({'mesh': mi, 'primitive': pi, 'input': len(t), 'output': len(f), **decision})
    for node in changed['nodes']:
        if 'mesh' in node:
            e = node.setdefault('extras', {})
            if 'native_shell_index' in e:
                e['source_native_shell_index'] = e.pop('native_shell_index')
            e.update(inspection_only=True, derived_geometry=True, native_identity_claim=False)
    changed.setdefault('asset', {}).setdefault('extras', {}).update(
        inspection_only=True, collision_approved=False, visual_lod_target_ratio=ratio)
    mesh_remap = {old: new for new, old in enumerate(sorted(
        {n['mesh'] for n in changed['nodes'] if 'mesh' in n}))}
    payload = compact(changed, binary); write_glb(target, changed, payload)
    # Verify the actual exported payload, including all retained attribute values.
    actual, ab = read_glb(target)
    if actual['materials'] != doc['materials']:
        raise ValueError('material table changed')
    for record in records:
        old = doc['meshes'][record['mesh']]['primitives'][record['primitive']]
        new = actual['meshes'][mesh_remap[record['mesh']]]['primitives'][record['primitive']]
        used, inv = expected[record['mesh'], record['primitive']]
        if not np.array_equal(accessor(actual, ab, new['indices']), inv):
            raise ValueError('exported indices mismatch')
        for key, index in old['attributes'].items():
            if not np.array_equal(accessor(actual, ab, new['attributes'][key]), accessor(doc, blob, index)[used]):
                raise ValueError('exported attribute mismatch')
    return {'target_ratio': ratio, 'placed_triangles': scene_triangles(actual),
            'stored_triangles': sum(r['output'] for r in records),
            'bytes': target.stat().st_size, 'primitives': records,
            'exported_attributes_verified': True}
