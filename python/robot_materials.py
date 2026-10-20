# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reversible robot display materials; source paint and geometry stay intact.

Names refer to leaf parts, never entire ancestor assemblies. Dimensional rules
are limited to named AM02 modules and reviewed wheel products. These are visual
interpretations, not measured physical compositions or referee light states.
"""
import copy
from collections import Counter
import re

import numpy as np

from gltf_scene import accessor, scene_nodes
from robot_reference_geometry import triangle_components

PALETTE = {
    'rubber': ([.065, .069, .075], 0., .88),
    'carbon': ([.10, .115, .13], 0., .38),
    'aluminum': ([.66, .69, .73], .8, .34),
    'steel': ([.40, .43, .47], .85, .32),
    'printed-polymer': ([.22, .24, .27], 0., .75),
    'armor-housing': ([.10, .11, .13], 0., .5),
    'armor-face': ([.19, .20, .22], 0., .65),
    'team-diffuser': ([.95, .13, .10], 0., .4),
    'unknown-neutral': ([.40, .42, .45], .15, .55),
}


def linear(value):
    """Convert an sRGB channel into glTF linear light."""
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def eligible(material):
    """Only unstyled faces and the reviewed uniform pale CAD tint may change."""
    extras = material.get('extras', {})
    return ((extras.get('step_colour_origin') == 'fallback' and extras.get('step_colour_srgb') is None)
            or (extras.get('step_colour_origin') == 'source'
                and extras.get('step_colour_srgb') == [.7922, .8196, .9333]))


def classify(name, size_mm):
    """Return display role and evidence from a leaf name and sorted PCA extent."""
    a, b, c = size_mm
    # These selectors apply only inside complete named detector modules, not
    # their support plates. AM02 has a thin face, shell, two diffusers and lugs.
    if re.search(r'装甲模块AM02|小装甲板模块|小装甲板AM02|^大装甲$', name, re.I):
        if 12 < a < 16 and 16 < b < 20 and 57 < c < 62:
            return 'team-diffuser', 'named AM02: reviewed 59 mm diffuser envelope'
        if a < 5 and b > 110 and c > 125:
            return 'armor-face', 'named AM02: thin detector face'
        if 9 < a < 17 and b > 110 and c > 125:
            return 'armor-housing', 'named AM02: outer housing'
        return 'aluminum', 'named AM02: mounting hardware; no whole-assembly tint'
    if re.fullmatch('左旋麦轮|右旋麦轮', name):
        if 16 < a < 20 and 16 < b < 20 and 36 < c < 41:
            return 'rubber', 'reviewed mecanum roller outer sleeve; inner hub excluded'
        return 'aluminum', 'reviewed mixed mecanum wheel: non-roller hardware'
    if re.search(r'pu620040-12', name, re.I):
        return ('rubber', '40 mm urethane outer sleeve') if 36 < b < 43 else ('steel', 'retained inner bearing')
    if re.search(r'PU62520-6', name, re.I):
        return ('rubber', '20 mm urethane outer sleeve') if 18 < b < 23 else ('steel', 'retained inner bearing')
    if name == '全向轮整个':
        if 17 < a < 23 and 17 < b < 23 and 17 < c < 24:
            return 'rubber', 'reviewed Future omni wheel: 20 mm individual roller'
        return 'aluminum', 'reviewed Future omni wheel: hub and side plates'
    if name in ('内嵌麦轮', '履带麦轮'):
        if 34 < a < 42 and 145 < b < 160 and 145 < c < 160:
            return 'rubber', 'reviewed Hero wheel: continuous tread body; separate side plates retained'
        return 'aluminum', 'reviewed Hero wheel: separate wheel side plate'
    if name == '注塑滚子' or name == '聚氨酯包胶' or name.startswith('全向轮滚子-0517_'):
        return 'rubber', 'explicit roller/urethane leaf'
    # Carbon-tube clamps and attachment plates are not carbon tubes themselves.
    if re.search('碳', name) and not re.search('夹|固定|安装|支架|中心储矿', name):
        return 'carbon', 'explicit carbon tube/plate leaf'
    if re.search('碳板', name):
        return 'carbon', 'explicit carbon plate leaf'
    if re.search('打印', name):
        return 'printed-polymer', 'explicit printed part leaf'
    if re.search('铝|机加|钣金|碳管.*管夹', name):
        return 'aluminum', 'explicit aluminum/machined/sheet/clamp leaf'
    if re.search('钢|轴承|螺|垫圈|ISO |DIN |GB[ /T]|齿轮|导轨', name, re.I):
        return 'steel', 'named metal hardware leaf'
    return 'unknown-neutral', 'unspecified physical material; neutral display only'


def split_wheel_shells(document, binary, lookup):
    """Split reviewed HEXROLL shell rollers from hubs by connected components.

    The narrow selector is confined to named imported wheel shells. It appends
    index subsets only, retaining every face once and all original attributes.
    """
    payload = bytearray(binary)
    for index, _, _ in list(scene_nodes(document)):
        node = document['nodes'][index]
        names = [lookup[p]['name'] for p in node.get('extras', {}).get('source_occurrence_paths', []) if p in lookup]
        if 'mesh' not in node or not names or not all(n in ('HEXROLL-Left', 'HEXROLL-Right') for n in names):
            continue
        mesh = copy.deepcopy(document['meshes'][node['mesh']])
        primitives = []
        for primitive in mesh['primitives']:
            if not eligible(document['materials'][primitive['material']]):
                primitives.append(primitive)
                continue
            points = accessor(document, binary, primitive['attributes']['POSITION'])
            triangles = accessor(document, binary, primitive['indices']).reshape(-1, 3)
            rubber = np.zeros(len(triangles), dtype=bool)
            for mask in triangle_components(points, triangles):
                q = points[np.unique(triangles[mask])]
                _, _, axes = np.linalg.svd(q - q.mean(0), full_matrices=False)
                a, b, c = np.sort(np.ptp(q @ axes.T, axis=0) * 1000)
                if 15 < a < 21 and 16 < b < 22 and 36 < c < 46:
                    rubber |= mask
            if not rubber.any():
                primitives.append(primitive)
                continue
            for mask, role in [(rubber, 'rubber'), (~rubber, 'unknown-neutral')]:
                if not mask.any():
                    continue
                part = copy.deepcopy(primitive)
                indices = triangles[mask].astype('<u4').reshape(-1)
                payload.extend(b'\0' * (-len(payload) % 4))
                offset = len(payload); payload.extend(indices.tobytes())
                view = len(document['bufferViews'])
                document['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': indices.nbytes, 'target': 34963})
                part['indices'] = len(document['accessors'])
                document['accessors'].append({'bufferView': view, 'componentType': 5125, 'count': len(indices), 'type': 'SCALAR'})
                part.setdefault('extras', {})['reviewed_display_role'] = [role, 'HEXROLL shell: connected roller sleeves; all other surfaces retained']
                primitives.append(part)
        mesh['primitives'] = primitives
        node['mesh'] = len(document['meshes']); document['meshes'].append(mesh)
    document['buffers'][0]['byteLength'] = len(payload)
    return bytes(payload)


def apply_materials(document, binary, rows):
    """Append role materials/mesh bindings without modifying source resources.

    Existing materials remain byte-for-byte JSON equal; overrides store their
    original PBR, source material index and evidence. Shared source meshes are
    cloned for each distinct material binding. All original geometry accessors/bytes,
    transforms, and hierarchy remain unchanged. Shell index subsets may append
    index buffers; their union is exactly the original triangles.
    """
    lookup = {r['path']: r for r in rows}
    binary = split_wheel_shells(document, binary, lookup)
    counts = Counter()
    assignments = []
    material_cache, mesh_cache = {}, {}
    for index, _, _ in list(scene_nodes(document)):
        node = document['nodes'][index]
        if 'mesh' not in node:
            continue
        paths = node.get('extras', {}).get('source_occurrence_paths', [])
        names = [lookup[p]['name'] if p in lookup else node.get('extras', {}).get('source_definition_name', '') for p in paths]
        mesh_index = node['mesh']
        original = document['meshes'][mesh_index]
        mesh = copy.deepcopy(original)
        changed = False
        for pi, primitive in enumerate(mesh['primitives']):
            mi = primitive.get('material')
            if mi is None or not eligible(document['materials'][mi]):
                counts['source-painted'] += 1
                continue
            p = accessor(document, binary, primitive['attributes']['POSITION'])
            _, _, axes = np.linalg.svd(p - p.mean(0), full_matrices=False)
            size = np.sort(np.ptp(p @ axes.T, axis=0) * 1000)
            proposals = [classify(name, size) for name in names] or [classify('', size)]
            role, evidence = primitive.get('extras', {}).get('reviewed_display_role', proposals[0]) if len(set(proposals)) == 1 else ('unknown-neutral', 'ambiguous source aliases')
            # Original per-face source paint still takes precedence above.
            key = mi, role
            if key not in material_cache:
                material = copy.deepcopy(document['materials'][mi])
                rgb, metallic, roughness = PALETTE[role]
                material['name'] = 'robot-display/' + role
                extras = material.setdefault('extras', {})
                extras['display_override'] = {'policy': 'robot-materials-v1', 'role': role,
                    'source_material': mi, 'original_pbr': copy.deepcopy(material.get('pbrMetallicRoughness', {})),
                    'srgb': rgb, 'inferred_display_only': True}
                material['pbrMetallicRoughness'] = {'baseColorFactor': [*[linear(v) for v in rgb], 1.],
                    'metallicFactor': metallic, 'roughnessFactor': roughness}
                material_cache[key] = len(document['materials'])
                document['materials'].append(material)
            primitive['material'] = material_cache[key]
            counts[role] += 1
            assignments.append({'node': index, 'primitive': pi, 'paths': paths, 'names': names,
                                'role': role, 'evidence': evidence, 'pca_extent_mm': size.tolist()})
            changed = True
        if changed:
            key = mesh_index, tuple(p.get('material') for p in mesh['primitives'])
            if key not in mesh_cache:
                mesh_cache[key] = len(document['meshes'])
                document['meshes'].append(mesh)
            node['mesh'] = mesh_cache[key]
    return binary, {'policy': 'robot-materials-v1', 'primitive_counts': dict(counts),
            'assignments': assignments, 'geometry_unchanged': True,
            'team_diffuser_color': 'illustrative red; no live team or referee state binding'}


def verify_materials(original, original_binary, styled, binary):
    """Assert exact triangle multiplicity, source attributes and node transforms."""
    import json
    assert binary[:len(original_binary)] == original_binary
    for field in ('materials', 'meshes', 'accessors', 'bufferViews'):
        assert styled[field][:len(original[field])] == original[field], field
    assert len(styled['nodes']) == len(original['nodes'])
    for before, after in zip(original['nodes'], styled['nodes']):
        assert {k: v for k, v in before.items() if k != 'mesh'} == {k: v for k, v in after.items() if k != 'mesh'}
        if 'mesh' not in before:
            continue
        def groups(document, payload, node):
            result = {}
            for p in document['meshes'][node['mesh']]['primitives']:
                # Attributes include normals/UVs; everything except appearance
                # and the split index accessor must retain the original binding.
                key = json.dumps({k: v for k, v in p.items() if k not in ('material', 'indices', 'extras')}, sort_keys=True)
                result.setdefault(key, []).append(accessor(document, payload, p['indices']).reshape(-1, 3))
            ordered = {}
            for key, chunks in result.items():
                triangles = np.concatenate(chunks)
                ordered[key] = triangles[np.lexsort(triangles.T[::-1])]
            return ordered
        a, b = groups(original, original_binary, before), groups(styled, binary, after)
        assert a.keys() == b.keys()
        for key in a:
            np.testing.assert_array_equal(a[key], b[key])
    for field in ('scenes', 'scene', 'animations', 'skins'):
        assert styled.get(field) == original.get(field), field
    return {'source_materials_preserved': True, 'original_binary_prefix_preserved': True,
            'exact_triangle_multiplicity_preserved': True, 'attributes_preserved': True,
            'hierarchy_and_transforms_preserved': True}
