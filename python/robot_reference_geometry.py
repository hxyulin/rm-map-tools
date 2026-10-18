# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Remove reviewed CAD reference bodies without editing retained physical surfaces.

Selectors are scoped to a checksum-pinned source and an audited occurrence name.
Shape/name heuristics are evidence for review, never an automatic deletion rule.
Raw source files remain intact. Derived exports retain source anchors and copy
live vertex attributes exactly; unused mesh/buffer resources are pruned.
"""
import copy

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from gltf_scene import accessor


def triangle_components(points, triangles):
    """Connected triangle masks, welding flat-shading duplicates within one micron."""
    vertices, inverse = np.unique(np.round(points * 1e6).astype(np.int64), axis=0, return_inverse=True)
    welded = inverse[triangles]
    a = np.concatenate([welded[:, 0], welded[:, 1], welded[:, 2]])
    b = np.concatenate([welded[:, 1], welded[:, 2], welded[:, 0]])
    graph = coo_matrix((np.ones(len(a)), (a, b)), shape=(len(vertices), len(vertices)))
    _, labels = connected_components(graph, directed=False)
    return [labels[welded[:, 0]] == label for label in np.unique(labels[welded[:, 0]])]


def _triangle_count(document, node):
    return sum(document['accessors'][p['indices']]['count'] // 3
               for p in document['meshes'][node['mesh']]['primitives'])


def apply_reference_exclusions(document, binary, rows, policy, source_center_mm=None):
    """Apply reviewed whole-solid/component selectors, failing closed on drift.

    Whole-leaf exclusion is deliberately unsupported: a leaf labelled mounting
    requirements can contain the real controller, camera or positioning module.
    """
    if not policy:
        return binary, []
    by_path = {r['path']: r for r in rows}
    report = []
    for rule in policy:
        path = rule['path']
        row = by_path.get(path)
        if row is None or row['name'] != rule['expected_name']:
            raise ValueError('reference selector source name/path mismatch')
        if not rule.get('reason'):
            raise ValueError('reference exclusion needs reviewed evidence')
        matches = []
        for index, node in enumerate(document['nodes']):
            if 'mesh' not in node:
                continue
            extras = node.get('extras', {})
            sid = extras.get('native_solid_index')
            if rule.get('solid') is not None:
                selected = sid == rule['solid'] and sid in row.get('native_solids', [])
            else:
                selected = extras.get('source_leaf_path') == path
            if selected:
                matches.append((index, node))
        if len(matches) != 1:
            raise ValueError('reference selector must match exactly one source mesh node')
        index, node = matches[0]
        before = _triangle_count(document, node)
        record = {'path': path, 'name': row['name'], 'reason': rule['reason'],
                  'node': index, 'native_solid_index': node['extras']['native_solid_index']}
        if rule.get('solid') is not None and 'source_local_plane' not in rule:
            if before != rule['expected_triangles']:
                raise ValueError('reference solid triangle count changed; review again')
            node.pop('mesh')
            node['extras']['reference_geometry_excluded'] = record.copy()
            removed = before
        else:
            mesh = copy.deepcopy(document['meshes'][node['mesh']])
            if len(mesh['primitives']) != 1:
                raise ValueError('component selector requires a single material primitive')
            primitive = mesh['primitives'][0]
            points = accessor(document, binary, primitive['attributes']['POSITION'])
            indices = accessor(document, binary, primitive['indices'])
            triangles = indices.astype(np.int64).reshape(-1, 3)
            if 'source_local_plane' in rule:
                if source_center_mm is None or 'placement' not in row:
                    raise ValueError('local-plane selection needs the audited source frame')
                plane = rule['source_local_plane']
                placement = np.asarray(row['placement'], dtype=float)
                local_mm = (points * 1000 + np.asarray(source_center_mm) - placement[:, 3]) @ placement[:, :3]
                mask = np.max(local_mm[triangles, plane['axis']], axis=1) > plane['above_mm']
                if int(mask.sum()) != rule['expected_triangles']:
                    raise ValueError('reference plane selection changed; review again')
            else:
                candidates = []
                for mask in triangle_components(points, triangles):
                    used = points[np.unique(triangles[mask])]
                    if mask.sum() == rule['expected_triangles'] and np.allclose(
                            np.ptp(used, axis=0) * 1000, rule['extent_mm'], atol=.1, rtol=0):
                        candidates.append(mask)
                if len(candidates) != 1:
                    raise ValueError('reference component geometry changed; review again')
                mask = candidates[0]
            retained = triangles[~mask].astype(indices.dtype).reshape(-1)
            if not len(retained):
                raise ValueError('component exclusion must retain physical module geometry')
            # Append only the changed index list. Every retained vertex, normal,
            # material, placement and original buffer byte remains unchanged.
            payload = bytearray(binary)
            payload.extend(b'\0' * (-len(payload) % 4))
            offset = len(payload)
            payload.extend(retained.tobytes())
            payload.extend(b'\0' * (-len(payload) % 4))
            view = len(document['bufferViews'])
            document['bufferViews'].append({'buffer': 0, 'byteOffset': offset,
                                            'byteLength': retained.nbytes, 'target': 34963})
            acc = copy.deepcopy(document['accessors'][primitive['indices']])
            acc.update(bufferView=view, byteOffset=0, count=len(retained))
            acc.pop('min', None)
            acc.pop('max', None)
            primitive['indices'] = len(document['accessors'])
            document['accessors'].append(acc)
            node['mesh'] = len(document['meshes'])
            document['meshes'].append(mesh)
            document['buffers'][0]['byteLength'] = len(payload)
            binary = bytes(payload)
            removed = int(mask.sum())
            node['extras']['reference_component_excluded'] = record.copy()
        record.update(removed_triangles=removed, retained_triangles=before - removed)
        report.append(record)
    return binary, report


def verify_reference_cleanup(original, original_binary, cleaned, cleaned_binary, report):
    """Verify removed counts and exact retained indices, attributes, materials and poses."""
    from collections import Counter
    if original.get('materials', []) != cleaned.get('materials', []):
        raise ValueError('cleanup modified source materials')
    by_node = {r['node']: r for r in report}
    if len(by_node) != len(report):
        raise ValueError('cleanup report must have unique node ownership')
    removed = retained = 0
    for index, node in enumerate(original['nodes']):
        if 'mesh' not in node:
            continue
        target = cleaned['nodes'][index]
        entry = by_node.get(index)
        for key in ['matrix', 'translation', 'rotation', 'scale']:
            if node.get(key) != target.get(key):
                raise ValueError('cleanup moved a physical source part')
        if 'mesh' not in target:
            count = _triangle_count(original, node)
            if entry is None or entry['removed_triangles'] != count or entry['retained_triangles'] != 0:
                raise ValueError('unreported complete source removal')
            removed += count
            continue
        before = original['meshes'][node['mesh']]['primitives']
        after = cleaned['meshes'][target['mesh']]['primitives']
        if len(before) != len(after):
            raise ValueError('cleanup changed source primitive count')
        node_removed = node_retained = 0
        for a, b in zip(before, after):
            if a.get('material') != b.get('material') or a['attributes'].keys() != b['attributes'].keys():
                raise ValueError('cleanup changed source appearance/attribute ownership')
            for name, acc in a['attributes'].items():
                if not np.array_equal(accessor(original, original_binary, acc),
                                      accessor(cleaned, cleaned_binary, b['attributes'][name])):
                    raise ValueError('cleanup changed a retained vertex attribute')
            first = accessor(original, original_binary, a['indices']).reshape(-1, 3)
            second = accessor(cleaned, cleaned_binary, b['indices']).reshape(-1, 3)
            left = Counter(map(tuple, first.tolist()))
            right = Counter(map(tuple, second.tolist()))
            if right - left:
                raise ValueError('cleanup introduced or rewrote triangles')
            node_removed += len(first) - len(second)
            node_retained += len(second)
        if node_removed != (entry['removed_triangles'] if entry else 0):
            raise ValueError('cleanup removed unreported triangles')
        if entry and node_retained != entry['retained_triangles']:
            raise ValueError('cleanup retained count mismatch')
        removed += node_removed
        retained += node_retained
    return {'removed_reference_triangles': removed, 'retained_triangles': retained,
            'retained_vertex_attributes_exact': True, 'source_materials_exact': True,
            'source_part_local_poses_exact': True,
            'original_buffer_prefix_exact': cleaned_binary[:len(original_binary)] == original_binary}


def compact_reference_resources(document, binary):
    """Drop unused mesh/accessor/buffer resources after removing reference geometry.

    Copy live buffer views byte-for-byte; indices within a retained primitive,
    vertex attributes, node indices, transforms and materials stay unchanged.
    This candidate pass supports rigid meshes and embedded buffers only.
    """
    from gltf_scene import scene_nodes
    if document.get('animations') or document.get('skins') or len(document.get('buffers', [])) != 1:
        raise ValueError('reference compaction expects a rigid single-buffer candidate')
    live_meshes = sorted({document['nodes'][i]['mesh'] for i, _, _ in scene_nodes(document)
                          if 'mesh' in document['nodes'][i]})
    mesh_map = {old: new for new, old in enumerate(live_meshes)}
    meshes = [copy.deepcopy(document['meshes'][i]) for i in live_meshes]
    needed = set()
    for mesh in meshes:
        for primitive in mesh['primitives']:
            if primitive.get('targets'):
                raise ValueError('reference compaction does not handle morph targets')
            needed.update(primitive['attributes'].values())
            needed.add(primitive['indices'])
    accessors = [copy.deepcopy(document['accessors'][i]) for i in sorted(needed)]
    accessor_map = {old: new for new, old in enumerate(sorted(needed))}
    views = {a['bufferView'] for a in accessors}
    views.update(i['bufferView'] for i in document.get('images', []) if 'bufferView' in i)
    view_map = {old: new for new, old in enumerate(sorted(views))}
    payload = bytearray()
    output_views = []
    for index in sorted(views):
        view = copy.deepcopy(document['bufferViews'][index])
        if view.get('buffer', 0) != 0:
            raise ValueError('external buffer in reference candidate')
        payload.extend(b'\0' * (-len(payload) % 4))
        start = view.get('byteOffset', 0)
        chunk = binary[start:start + view['byteLength']]
        if len(chunk) != view['byteLength']:
            raise ValueError('reference candidate buffer view is truncated')
        view['byteOffset'] = len(payload)
        payload.extend(chunk)
        output_views.append(view)
    payload.extend(b'\0' * (-len(payload) % 4))
    for node in document['nodes']:
        if 'mesh' in node:
            if node['mesh'] not in mesh_map:
                raise ValueError('unreachable mesh node in reference candidate')
            node['mesh'] = mesh_map[node['mesh']]
    for mesh in meshes:
        for primitive in mesh['primitives']:
            primitive['attributes'] = {k: accessor_map[v] for k, v in primitive['attributes'].items()}
            primitive['indices'] = accessor_map[primitive['indices']]
    for acc in accessors:
        acc['bufferView'] = view_map[acc['bufferView']]
    for image in document.get('images', []):
        if 'bufferView' in image:
            image['bufferView'] = view_map[image['bufferView']]
    document.update(meshes=meshes, accessors=accessors, bufferViews=output_views)
    document['buffers'][0]['byteLength'] = len(payload)
    return bytes(payload)
