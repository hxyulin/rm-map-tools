# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Identify source armor surfaces and export reversible simulator mount bindings.

Detection regions remain a rules choice, separate from a fitted physical shell.
Only reviewed AM02/AM12 leaves (or the pinned Zhulong chassis) are considered.
Source brackets and mounting hardware are retained.
"""
import copy
import re

import numpy as np
from scipy.spatial.transform import Rotation

from gltf_scene import mesh_instances

MODULE_NAME = re.compile(r'装甲模块AM02|小装甲板模块|小装甲板AM02|^大装甲$')


def frame_from_face(points):
    """Fit a thin face in Y-up GLB space; +x outward, +y width, +z up."""
    unique = np.unique(points, axis=0)
    _, _, axes = np.linalg.svd(unique - unique.mean(0), full_matrices=False)
    normal = axes[-1]
    center = (points.min(0) + points.max(0)) / 2
    outward = center * [1, 0, 1]
    if np.linalg.norm(outward) < .05:
        raise ValueError('armor face is too close to the robot center to orient')
    if normal @ outward < 0:
        normal = -normal
    up = np.array([0., 1., 0.])
    up -= normal * (up @ normal)
    up /= np.linalg.norm(up)
    width = np.cross(up, normal)
    basis = np.column_stack([normal, width, up])
    local = points @ basis
    lower, upper = local.min(0), local.max(0)
    origin = basis @ np.array([upper[0], (lower[1] + upper[1]) / 2, (lower[2] + upper[2]) / 2])
    return origin, basis, upper - lower


def identify_armor(document, binary, rows=(), *, zhulong=False):
    """Return one mount per physical source face, with exact replacement selectors.

    Coordinates are in the exported GLB world frame. Source aliases deduplicate
    by their single attached mesh node. Ambiguous multi-face leaves fail closed.
    """
    lookup = {r['path']: r['name'] for r in rows}
    if zhulong:
        return identify_zhulong(document, binary)
    parts = []
    for ni, pi, points, triangles, mi in mesh_instances(document, binary):
        node = document['nodes'][ni];extra = node.get('extras', {})
        paths = extra.get('source_occurrence_paths', [extra.get('source_occurrence_path', '')])
        names = [lookup.get(p, extra.get('source_definition_name', '')) for p in paths]
        if not any(MODULE_NAME.search(n) for n in names):
            continue
        _, _, axes = np.linalg.svd(points - points.mean(0), full_matrices=False)
        size = np.sort(np.ptp(points @ axes.T, axis=0))
        parts.append({'node': ni, 'primitive': pi, 'points': points, 'size': size,
                      'paths': paths, 'names': names, 'extras': extra, 'triangles': len(triangles)})
    faces = [p for p in parts if .002 < p['size'][0] < .0045
             and .125 < p['size'][1] < .145 and .125 < p['size'][2] < .245]
    mounts = []
    used = set()
    for face in faces:
        origin, basis, span = frame_from_face(face['points'])
        kind = 'AM12' if span[1] > .18 else 'AM02'
        # The two official carrier lugs (~3 x 34 x 45 mm) deliberately do not
        # match. Replace only the shell, detector face and light covers.
        removed = []
        for p in parts:
            if not set(p['paths']) & set(face['paths']):
                continue
            size = p['size']
            shell = .009 < size[0] < .017 and size[1] > .11 and size[2] > .125
            diffuser = .012 < size[0] < .016 and .016 < size[1] < .020 and .057 < size[2] < .062
            if p is not face and not shell and not diffuser:
                continue
            local = (p['points'] - origin) @ basis
            width = .125 if kind == 'AM12' else .08
            if (local[:, 0].min() < -.035 or local[:, 0].max() > .010
                    or np.abs(local[:, 1]).max() > width or np.abs(local[:, 2]).max() > .08):
                continue
            key = p['node'], p['primitive']
            if key in used:
                raise ValueError('overlapping armor replacement membership')
            used.add(key)
            removed.append({'node': key[0], 'primitive': key[1],
                            'native_solid_index': p['extras'].get('native_solid_index'),
                            'triangles': p['triangles']})
        if len(removed) != 4:
            raise ValueError(f'expected face, shell and two diffusers at {face["paths"]}, got {len(removed)}')
        # Retain the fitted small housing contract. AM12 uses the guide's
        # 235 x 127 mm outline with the same conservative housing depth.
        width = .235 if kind == 'AM12' else .141
        quat = Rotation.from_matrix(basis).as_quat()
        mounts.append({'id': len(mounts), 'kind': kind, 'source_paths': face['paths'],
            'face_matrix_gltf': np.block([[basis, origin[:, None]], [np.array([[0, 0, 0, 1]])]]).flatten(order='F').tolist(),
            'face_pose_gltf': {'translation_m': origin.tolist(), 'rotation_wxyz': quat[[3, 0, 1, 2]].tolist()},
            'housing_half_m': [.0095, width / 2, .0635 if kind == 'AM12' else .0675],
            'face_size_m': [.223 if kind == 'AM12' else .128, .113],
            'light_span_m': .225 if kind == 'AM12' else .130, 'light_length_m': .056,
            'source_face_size_m': span[1:].tolist(),
            'motion_group': face['extras'].get('motion_group', 'unbound'),
            'replace_surfaces': removed, 'source_hardware_retained': True})
    return {'schema': 'robot-armor-v1', 'frame': 'GLB world metres; face local +x outward, +y width, +z up',
            'modules': mounts, 'scoring_policy': 'existing simulator small detector until a rules-specific AM12 region is bound',
            'scope': 'Fitted source surfaces and physical housing mounts; not automatic chassis admission or rule compliance.'}


def strip_armor_surfaces(document, report):
    """Remove identified surface primitives, leaving source carriers and anchors."""
    grouped = {}
    for mount in report['modules']:
        for part in mount['replace_surfaces']:
            grouped.setdefault(part['node'], set()).add(part['primitive'])
    for ni, excluded in grouped.items():
        node = document['nodes'][ni]
        mesh = copy.deepcopy(document['meshes'][node['mesh']])
        mesh['primitives'] = [p for pi, p in enumerate(mesh['primitives']) if pi not in excluded]
        if mesh['primitives']:
            node['mesh'] = len(document['meshes']);document['meshes'].append(mesh)
        else:
            del node['mesh']
        node.setdefault('extras', {})['armor_replacement'] = {'policy': 'robot-armor-v1', 'primitives': sorted(excluded)}


def identify_zhulong(document, binary):
    """Bind four whole-module solids in the pinned, flattened Zhulong assembly.

    Its source names are damaged by the CAD encoding and each module is one
    merged solid. The reviewed solid IDs replace fuzzy name/shape inference.
    """
    by_solid = {3: 2, 6: 0, 81: 1, 82: 3}
    modules = []
    for ni, pi, points, triangles, mi in mesh_instances(document, binary):
        e = document['nodes'][ni].get('extras', {})
        sid = e.get('native_solid_index')
        if e.get('source_id') != 'chassis' or sid not in by_solid:
            continue
        slot = by_solid[sid];yaw = slot * np.pi / 2
        normal = np.array([np.sin(yaw) * np.cos(np.pi/12), np.sin(np.pi/12), np.cos(yaw) * np.cos(np.pi/12)])
        up = np.array([0., 1., 0.]);up -= normal * (up @ normal);up /= np.linalg.norm(up)
        basis = np.column_stack([normal, np.cross(up, normal), up])
        q = points @ basis;lo, hi = q.min(0), q.max(0)
        origin = basis @ [hi[0], (lo[1]+hi[1])/2, (lo[2]+hi[2])/2]
        quat = Rotation.from_matrix(basis).as_quat()
        modules.append({'id': slot, 'kind': 'AM02', 'source_paths': [e['source_occurrence_path']],
            'face_matrix_gltf': np.block([[basis, origin[:, None]], [np.array([[0, 0, 0, 1]])]]).flatten(order='F').tolist(),
            'face_pose_gltf': {'translation_m': origin.tolist(), 'rotation_wxyz': quat[[3,0,1,2]].tolist()},
            'housing_half_m': [.0095, .0705, .0675], 'face_size_m': [.128, .113],
            'light_span_m': .130, 'light_length_m': .056, 'motion_group': 'body',
            'replace_surfaces': [{'node': ni, 'primitive': pi, 'native_solid_index': sid, 'triangles': len(triangles)}],
            'source_hardware_retained': True})
    if len(modules) != 4:
        raise ValueError('pinned Zhulong whole-module solids changed')
    return {'schema': 'robot-armor-v1', 'frame': 'GLB world metres; face local +x outward, +y width, +z up',
            'modules': sorted(modules, key=lambda m: m['id']),
            'scoring_policy': 'existing simulator small detector',
            'scope': 'Pinned whole-module solids; source-fitted hull fronts and 15 degree mount angle.'}


def merge_armor_aliases(report, aliases):
    """Merge explicitly reviewed overlapping source modules, checking pose drift."""
    for pair in aliases:
        primary = [m for m in report['modules'] if pair['primary'] in m['source_paths']]
        alias = [m for m in report['modules'] if pair['alias'] in m['source_paths']]
        if len(primary) != 1 or len(alias) != 1 or primary[0] is alias[0]:
            raise ValueError('ambiguous armor alias selector')
        a, b = primary[0], alias[0]
        am = np.array(a['face_matrix_gltf']).reshape(4,4,order='F')
        bm = np.array(b['face_matrix_gltf']).reshape(4,4,order='F')
        distance = np.linalg.norm(am[:3,3] - bm[:3,3])
        if a['kind'] != b['kind'] or distance > .002 or np.max(np.abs(am[:3,:3] - bm[:3,:3])) > .01:
            raise ValueError('armor alias no longer coincides with its reviewed mount')
        a.setdefault('reviewed_aliases', []).append({'source_paths': b['source_paths'], 'distance_m': float(distance)})
        a['replace_surfaces'].extend(b['replace_surfaces'])
        report['modules'].remove(b)
    for i, m in enumerate(report['modules']):
        m['id'] = i


def verify_armor_replacement(original, stripped, report):
    """Check exact retained primitives, materials, nodes and source attributes."""
    removed = {}
    for m in report['modules']:
        for p in m['replace_surfaces']:
            removed.setdefault(p['node'], set()).add(p['primitive'])
    assert len(original['nodes']) == len(stripped['nodes'])
    for field in ('materials', 'accessors', 'bufferViews', 'buffers', 'scenes', 'animations'):
        assert original.get(field) == stripped.get(field), field
    for i, (a, b) in enumerate(zip(original['nodes'], stripped['nodes'])):
        for key, value in a.items():
            if key != 'mesh':
                if key == 'extras':
                    assert all(b[key][k] == v for k, v in value.items())
                else:
                    assert b[key] == value
        if 'mesh' not in a:
            assert 'mesh' not in b
            continue
        expected = [p for pi, p in enumerate(original['meshes'][a['mesh']]['primitives']) if pi not in removed.get(i,set())]
        actual = stripped['meshes'][b['mesh']]['primitives'] if 'mesh' in b else []
        assert actual == expected
    return {'only_selected_surfaces_removed': True, 'retained_primitives_and_attributes_exact': True,
            'source_hardware_and_transforms_preserved': True}
