# SPDX-License-Identifier: MIT OR Apache-2.0
"""Explicit, checksum-pinned triangle partitions for rigid semantic groups."""
import copy

import numpy as np

from gltf_scene import accessor, scene_nodes


def split_geometry(document, binary, spec):
    """Move selected triangles under another parent without changing their rest pose.

    Selectors/ranges refer to the original input. Ranges are half-open triangle
    ordinals, not vertex IDs. No geometric heuristic is evaluated at export time.
    """
    from export_semantics import resolve
    groups = spec.get('geometry_groups', [])
    if not groups:
        return document, binary, spec
    doc, resolved = copy.deepcopy(document), copy.deepcopy(spec)
    nodes, meshes = doc['nodes'], doc['meshes']
    world = {i: m for i, m, _ in scene_nodes(doc)}
    payload = bytearray(binary)
    selections, originals = {}, {}
    added = []

    def indexed(primitive, triangles):
        out = copy.deepcopy(primitive)
        while len(payload) % 4:
            payload.append(0)
        values = np.asarray(triangles, dtype='<u4').ravel()
        view = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(payload),
                                   'byteLength': values.nbytes, 'target': 34963})
        payload.extend(values.tobytes())
        out['indices'] = len(doc['accessors'])
        doc['accessors'].append({'bufferView': view, 'componentType': 5125,
                                'count': len(values), 'type': 'SCALAR'})
        return out

    for group in groups:
        source = resolve(document, group['select'])
        parent = resolve(document, group['parent'])
        if group['name'] in {n.get('name') for n in nodes}:
            raise ValueError('geometry group name already exists')
        if not group.get('evidence'):
            raise ValueError('geometry group requires evidence')
        source_mesh = document['meshes'][document['nodes'][source]['mesh']]
        if 'skin' in document['nodes'][source] or 'weights' in document['nodes'][source]:
            raise ValueError('cannot partition deformed geometry')
        primitives, provenance = [], []
        for selection in group['parts']:
            pi = selection['primitive']
            primitive = source_mesh['primitives'][pi]
            if primitive.get('mode', 4) != 4 or 'targets' in primitive:
                raise ValueError('only rigid triangle partitions are supported')
            key = source, pi
            if key not in originals:
                indices = (accessor(document, binary, primitive['indices']) if 'indices' in primitive
                           else np.arange(document['accessors'][primitive['attributes']['POSITION']]['count']))
                originals[key] = indices.reshape(-1, 3)
                selections[key] = np.zeros(len(originals[key]), bool)
            triangles = originals[key]
            mask = np.zeros(len(triangles), bool)
            ranges = selection.get('triangle_ranges', [[0, len(triangles)]])
            for lo, hi in ranges:
                if not isinstance(lo, int) or not isinstance(hi, int) or not 0 <= lo < hi <= len(mask) or mask[lo:hi].any():
                    raise ValueError('invalid/overlapping triangle ranges')
                mask[lo:hi] = True
            if not mask.any() or (selections[key] & mask).any():
                raise ValueError('empty or overlapping geometry groups')
            selections[key] |= mask
            primitives.append(copy.deepcopy(primitive) if mask.all() else indexed(primitive, triangles[mask]))
            provenance.append({'node': source, 'primitive': pi, 'triangle_ranges': ranges,
                               'triangle_count': int(mask.sum())})
        if not primitives:
            raise ValueError('empty geometry group')
        matrix = np.linalg.inv(world[parent]) @ world[source]
        index = len(nodes)
        nodes.append({'name': group['name'], 'matrix': matrix.flatten(order='F').tolist(),
                      'mesh': len(meshes), 'extras': {'source_geometry_partition': provenance}})
        meshes.append({'name': group['name'], 'primitives': primitives})
        nodes[parent].setdefault('children', []).append(index)
        added.append({'select': {'name': group['name']}, 'metadata': group['metadata'],
                      'evidence': group['evidence']})
    for source in {i for i, _ in selections}:
        primitives = []
        for pi, primitive in enumerate(document['meshes'][document['nodes'][source]['mesh']]['primitives']):
            key = source, pi
            if key not in selections:
                primitives.append(copy.deepcopy(primitive))
            elif not selections[key].all():
                primitives.append(indexed(primitive, originals[key][~selections[key]]))
        if primitives:
            nodes[source]['mesh'] = len(meshes)
            meshes.append({'name': nodes[source].get('name', ''), 'primitives': primitives})
        else:
            del nodes[source]['mesh']
    doc['buffers'][0]['byteLength'] = len(payload)
    resolved['nodes'] = resolved.get('nodes', []) + added
    return doc, bytes(payload), resolved
