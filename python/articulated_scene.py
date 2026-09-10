# SPDX-License-Identifier: MIT OR Apache-2.0
"""Rigid links derived from semantic GLB motion boundaries, without CAD imports."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from gltf_scene import local_matrix, mesh_instances, read_glb, scene_nodes


def checked_file(root, name, digest=None):
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError('asset path escapes package')
    if digest and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f'hash mismatch: {path}')
    return path


def rigid(matrix):
    matrix = np.asarray(matrix, float)
    if (matrix.shape != (4, 4) or not np.isfinite(matrix).all()
            or not np.allclose(matrix[3], [0, 0, 0, 1])
            or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(matrix[:3, :3]), 1, atol=1e-6)):
        raise ValueError('joint frames and placements must be rigid transforms')
    return matrix


def placement(record):
    if 'matrix_local_to_arena' in record:
        return rigid(record['matrix_local_to_arena'])
    return rigid(local_matrix({'translation': record.get('translation_m', [0, 0, 0]),
                               'rotation': record.get('rotation_xyzw', [0, 0, 0, 1])}))


def topology(document, binding):
    traversal = list(scene_nodes(document))
    worlds = {i: w for i, w, _ in traversal}
    joints = copy.deepcopy(binding.get('joints', []))
    ids = [j['id'] for j in joints]
    motions = [j['motion_node'] for j in joints]
    if len(set(ids)) != len(ids) or len(set(motions)) != len(motions):
        raise ValueError('duplicate joint ID or motion node')
    by_node = {j['motion_node']: j for j in joints}
    owners, links = {}, {'root': {'id': 'root', 'parent': None, 'rest': np.eye(4).tolist()}}
    for index, world, parent in traversal:
        owner = owners.get(parent, 'root')
        if index in by_node:
            j = by_node[index]
            if j['type'] not in ('continuous', 'revolute', 'prismatic'):
                raise ValueError('unsupported joint type')
            axis = np.asarray(j['axis'], float)
            if axis.shape != (3,) or not np.isfinite(axis).all() or not np.isclose(np.linalg.norm(axis), 1):
                raise ValueError('invalid joint axis')
            if parent != j['origin_node'] or not np.allclose(local_matrix(document['nodes'][index]), np.eye(4)):
                raise ValueError('joint motion node must be identity beneath its origin')
            if 'limits' in j:
                lo, hi = j['limits']
                if not np.isfinite([lo, hi]).all() or not lo <= 0 <= hi or j['type'] == 'continuous':
                    raise ValueError('invalid physical limits')
            rest = rigid(world)
            parent_rest = np.asarray(links[owner]['rest'])
            links[j['id']] = {'id': j['id'], 'parent': owner, 'rest': rest.tolist(),
                              'parent_to_joint': (np.linalg.inv(parent_rest) @ rest).tolist(), 'joint': j}
            owner = j['id']
        owners[index] = owner
    if set(motions) - worlds.keys():
        raise ValueError('joint outside selected scene')
    return links, owners


def link_poses(graph, coordinates=None):
    """Asset-local forward kinematics. Coordinates use metres and radians."""
    from scipy.spatial.transform import Rotation
    coordinates = coordinates or {}
    if set(coordinates) - (graph.keys() - {'root'}):
        raise ValueError('unknown joint coordinate')
    poses = {'root': np.eye(4)}
    for name, link in graph.items():
        if name == 'root':
            continue
        j = link['joint']
        q = float(coordinates.get(name, 0))
        if not np.isfinite(q) or ('limits' in j and not j['limits'][0] <= q <= j['limits'][1]):
            raise ValueError('invalid joint coordinate or outside physical limits')
        if q and j.get('geometry_binding') == 'frames_only':
            raise ValueError('frames-only joint has no verified moving geometry')
        delta = np.eye(4)
        if j['type'] == 'prismatic':
            delta[:3, 3] = np.asarray(j['axis']) * q
        else:
            delta[:3, :3] = Rotation.from_rotvec(np.asarray(j['axis']) * q).as_matrix()
        poses[name] = poses[link['parent']] @ np.asarray(link['parent_to_joint']) @ delta
    return poses


def extract_geometry(document, binary, binding, graph):
    own_graph, owners = topology(document, binding)
    if own_graph.keys() != graph.keys():
        raise ValueError('visual/collision joint IDs differ')
    for name in graph:
        a, b = own_graph[name], graph[name]
        if a['parent'] != b['parent'] or not np.allclose(a['rest'], b['rest'], atol=1e-6):
            raise ValueError('visual/collision joint frames differ')
        if name != 'root' and any(a['joint'].get(k) != b['joint'].get(k)
                                   for k in ('axis', 'type', 'limits', 'geometry_binding')):
            raise ValueError('visual/collision joint definitions differ')
    geometry = []
    for ni, pi, points, triangles, material in mesh_instances(document, binary):
        owner = owners[ni]
        inverse = np.linalg.inv(np.asarray(graph[owner]['rest']))
        points = points @ inverse[:3, :3].T + inverse[:3, 3]
        mat = document.get('materials', [])[material] if material is not None else {}
        color = mat.get('pbrMetallicRoughness', {}).get('baseColorFactor', [0.7, 0.7, 0.7, 1])
        geometry.append({'link': owner, 'node': ni, 'primitive': pi, 'points': points,
                         'triangles': triangles, 'color': color,
                         'metadata': document['nodes'][ni].get('extras', {})})
    return geometry


def load_asset(root, name, entry):
    ref = entry['semantics']
    sidepath = checked_file(root, ref['file'])
    sidecar = json.loads(sidepath.read_text())
    if sidecar.get('schema_version') != 1:
        raise ValueError('unsupported semantic schema')
    binding = sidecar['assets'][ref['asset']]
    docs, geometry = {}, {}
    for kind in ('visual', 'collision'):
        record = binding['files'][kind]
        path = checked_file(root, record['file'], record['sha256'])
        if path != checked_file(root, entry[kind], entry.get(kind + '_sha256')):
            raise ValueError('manifest and semantic file differ')
        docs[kind] = read_glb(path)
    graph, _ = topology(docs['visual'][0], binding['files']['visual'])
    for kind in docs:
        geometry[kind] = extract_geometry(*docs[kind], binding['files'][kind], graph)
    return {'name': name, 'graph': graph, 'geometry': geometry, 'documents': docs,
            'semantics': sidecar['assets'][ref['asset']],
            'placements': [placement(p).tolist() for p in entry.get('placements_in_source_arena_frame', [])],
            'source_entry': entry, 'source_directory': str(Path(root).resolve())}


def semantic_assets(root):
    """Load semantic assets, including the reference equipment subpackage."""
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    articulation = manifest.get('articulation', {})
    if articulation.get('file'):
        checked_file(root, articulation['file'], articulation.get('sha256'))
    for name, entry in manifest['assets'].items():
        if entry.get('semantics'):
            yield root, name, entry
    ref = manifest.get('reference_equipment')
    if ref:
        path = checked_file(root, ref['file'], ref.get('sha256'))
        yield from semantic_assets(path.parent)
