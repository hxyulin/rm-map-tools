# SPDX-License-Identifier: MIT OR Apache-2.0
"""GLB scene traversal shared by semantic and simulator exports. No CAD dependency."""
import json
from pathlib import Path
import struct

import numpy as np


def read_glb(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or struct.unpack_from('<III', data) != (0x46546C67, 2, len(data)):
        raise ValueError(f'invalid GLB: {path}')
    chunks, offset = {}, 12
    while offset < len(data):
        size, kind = struct.unpack_from('<II', data, offset)
        if size % 4 or offset + 8 + size > len(data) or kind in chunks:
            raise ValueError('invalid GLB chunk')
        chunks[kind] = data[offset + 8:offset + 8 + size]
        offset += 8 + size
    document = json.loads(chunks.pop(0x4E4F534A))
    if set(chunks) - {0x004E4942}:
        raise ValueError('unsupported GLB chunks')
    return document, chunks.get(0x004E4942, b'')


def write_glb(path, document, binary):
    js = json.dumps(document, separators=(',', ':'), allow_nan=False).encode()
    js += b' ' * (-len(js) % 4)
    binary += b'\0' * (-len(binary) % 4)
    chunks = struct.pack('<II', len(js), 0x4E4F534A) + js
    if binary:
        chunks += struct.pack('<II', len(binary), 0x004E4942) + binary
    Path(path).write_bytes(struct.pack('<III', 0x46546C67, 2, 12 + len(chunks)) + chunks)


def local_matrix(node):
    if 'matrix' in node:
        if any(k in node for k in ('translation', 'rotation', 'scale')):
            raise ValueError('node mixes matrix and TRS')
        result = np.asarray(node['matrix'], float).reshape(4, 4, order='F')
    else:
        x, y, z, w = node.get('rotation', [0, 0, 0, 1])
        if not np.isclose(x*x + y*y + z*z + w*w, 1, atol=1e-6):
            raise ValueError('non-unit quaternion')
        result = np.eye(4)
        result[:3, :3] = np.array([
            [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
        ]) @ np.diag(node.get('scale', [1, 1, 1]))
        result[:3, 3] = node.get('translation', [0, 0, 0])
    if not np.isfinite(result).all() or not np.allclose(result[3], [0, 0, 0, 1]):
        raise ValueError('invalid affine transform')
    return result


def scene_nodes(document):
    """Yield (node index, world matrix, parent index) in the selected scene."""
    nodes = document.get('nodes', [])
    roots = document['scenes'][document.get('scene', 0)]['nodes']
    seen = set()

    def walk(index, parent, matrix):
        if not isinstance(index, int) or index < 0 or index >= len(nodes) or index in seen:
            raise ValueError('scene contains an invalid, cyclic, or multiply parented node')
        seen.add(index)
        node = nodes[index]
        world = matrix @ local_matrix(node)
        yield index, world, parent
        for child in node.get('children', []):
            yield from walk(child, index, world)

    for root in roots:
        yield from walk(root, None, np.eye(4))


def accessor(document, binary, index):
    a = document['accessors'][index]
    if 'sparse' in a or 'bufferView' not in a:
        raise ValueError('sparse/unbacked accessors are unsupported')
    view = document['bufferViews'][a['bufferView']]
    if view.get('buffer', 0) != 0:
        raise ValueError('external buffers are unsupported')
    dtype = np.dtype({5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2',
                      5125: '<u4', 5126: '<f4'}[a['componentType']])
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
    stride = view.get('byteStride', dtype.itemsize * width)
    offset = a.get('byteOffset', 0)
    end = offset + max(0, a['count'] - 1) * stride + dtype.itemsize * width
    if stride < dtype.itemsize * width or end > view['byteLength']:
        raise ValueError('accessor exceeds buffer view')
    arr = np.ndarray((a['count'], width), dtype=dtype, buffer=binary,
                     offset=view.get('byteOffset', 0) + offset,
                     strides=(stride, dtype.itemsize))
    return arr[:, 0] if width == 1 else arr


def mesh_instances(document, binary):
    """Yield index, primitive index, transformed points, triangles, material index."""
    for index, world, _ in scene_nodes(document):
        node = document['nodes'][index]
        if 'skin' in node or 'weights' in node:
            raise ValueError('skinned or morphed nodes are unsupported')
        if 'mesh' not in node:
            continue
        for pi, primitive in enumerate(document['meshes'][node['mesh']]['primitives']):
            if primitive.get('mode', 4) != 4 or 'targets' in primitive:
                raise ValueError('only rigid triangle primitives are supported')
            points = accessor(document, binary, primitive['attributes']['POSITION']).astype(float)
            points = points @ world[:3, :3].T + world[:3, 3]
            indices = (accessor(document, binary, primitive['indices']) if 'indices' in primitive
                       else np.arange(len(points)))
            triangles = indices.astype(np.int64).reshape(-1, 3)
            used = np.unique(triangles)
            if len(used) != len(points):
                points = points[used]
                triangles = np.searchsorted(used, triangles)
            if np.linalg.det(world[:3, :3]) < 0:
                triangles = triangles[:, [0, 2, 1]]
            yield index, pi, points, triangles, primitive.get('material')


def read_glb_nodes(path):
    """Placed mesh instances with source sRGB color keys, preserving scene order."""
    document, binary = read_glb(path)
    grouped = {}
    for index, _, points, triangles, material in mesh_instances(document, binary):
        mat = document.get('materials', [])[material] if material is not None else {}
        rgb = mat.get('extras', {}).get('step_colour_srgb')
        if rgb is None:
            linear = mat.get('pbrMetallicRoughness', {}).get('baseColorFactor', [1, 1, 1, 1])[:3]
            rgb = [12.92*c if c <= 0.0031308 else 1.055*c**(1/2.4)-0.055 for c in linear]
        name = mat.get('name', '')
        key = name[len('colour_'):] if name.startswith('colour_') else ','.join(f'{c:.6f}' for c in rgb)
        if key == 'default':
            key = None
        grouped.setdefault(index, []).append((points, triangles, key))
    for index, parts in grouped.items():
        offsets = np.cumsum([0] + [len(p) for p, _, _ in parts[:-1]])
        yield (document['nodes'][index].get('name', f'node_{index}'),
               np.vstack([p for p, _, _ in parts]),
               np.vstack([t + offset for (_, t, _), offset in zip(parts, offsets)]),
               [key for _, t, key in parts for _ in t])
