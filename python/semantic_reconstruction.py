# SPDX-License-Identifier: MIT OR Apache-2.0
"""Add explicitly labelled reconstructions without changing original CAD meshes."""
import copy
from pathlib import Path

import numpy as np

from gltf_scene import accessor, local_matrix, read_glb


def tapered_prism(profile):
    sides = profile['sides']
    if not isinstance(sides, int) or not 3 <= sides <= 64:
        raise ValueError('prism sides must be an integer from 3 to 64')
    low, high = profile['z_range_m']
    lower, upper = profile['radius_m']
    center = np.asarray(profile['center_xy_m'], float)
    phase = profile.get('vertex_phase_rad', 0)
    if center.shape != (2,) or not np.isfinite([low, high, lower, upper, phase, *center]).all():
        raise ValueError('invalid prism dimensions')
    if low >= high or min(lower, upper) <= 0:
        raise ValueError('prism dimensions must be positive')
    angle = phase + np.arange(sides) * 2 * np.pi / sides
    ring = np.column_stack([np.cos(angle), np.sin(angle)])
    points = np.vstack([np.column_stack([center + ring * r, np.full(sides, z)])
                        for r, z in [(lower, low), (upper, high)]])
    triangles = []
    for i in range(sides):
        j = (i + 1) % sides
        triangles.extend([[i, j, j+sides], [i, j+sides, i+sides]])
    for i in range(1, sides-1):
        triangles.extend([[0, i+1, i], [sides, sides+i, sides+i+1]])
    # Separate vertices at sharp edges for flat face normals.
    xyz = points[np.asarray(triangles)].reshape(-1, 3)
    faces = xyz.reshape(-1, 3, 3)
    normals = np.cross(faces[:, 1]-faces[:, 0], faces[:, 2]-faces[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    return xyz, np.repeat(normals, 3, axis=0), np.arange(len(xyz)).reshape(-1, 3)


def add_reconstruction(document, binary, spec, source_root):
    """Append authored solids or pinned donor meshes; selectors use input nodes.

    copy_mesh matrices map donor mesh-local coordinates into the selected
    parent's coordinates. Donor ancestors are deliberately not copied.
    """
    from export_semantics import digest, resolve, safe_path
    additions = spec.get('geometry_additions', [])
    if not additions:
        return document, binary, spec
    doc, resolved = copy.deepcopy(document), copy.deepcopy(spec)
    payload = bytearray(binary)
    cache = {}

    def array(values, kind, component=5126):
        values = np.asarray(values, dtype='<f4' if component == 5126 else '<u4')
        payload.extend(b'\0' * (-len(payload) % 4))
        vi = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(payload), 'byteLength': values.nbytes})
        payload.extend(values.tobytes())
        ai = len(doc['accessors'])
        entry = {'bufferView': vi, 'componentType': component, 'count': len(values), 'type': kind}
        if kind == 'VEC3':
            entry.update(min=values.min(axis=0).tolist(), max=values.max(axis=0).tolist())
        doc['accessors'].append(entry)
        return ai

    def primitive(points, normals, indices, material):
        result = {'attributes': {'POSITION': array(points, 'VEC3')},
                  'indices': array(np.asarray(indices).ravel(), 'SCALAR', 5125), 'material': material}
        if normals is not None:
            result['attributes']['NORMAL'] = array(normals, 'VEC3')
        return result

    for addition in additions:
        if not addition.get('evidence') or addition['metadata'].get('layer') != 'reconstruction':
            raise ValueError('reconstruction requires evidence and its own layer')
        if addition['name'] in {n.get('name') for n in doc['nodes']}:
            raise ValueError('reconstruction name already exists')
        parent = resolve(document, addition['parent'])
        provenance = {'geometry_origin': 'reconstruction', 'kind': addition['type'],
                      'evidence': addition['evidence']}
        if addition['type'] == 'tapered_prism':
            points, normals, indices = tapered_prism(addition['profile'])
            material = len(doc.setdefault('materials', []))
            doc['materials'].append(copy.deepcopy(addition['material']))
            mi = len(doc['meshes'])
            doc['meshes'].append({'primitives': [primitive(points, normals, indices, material)]})
            provenance['profile'] = addition['profile']
        elif addition['type'] == 'copy_mesh':
            source = addition['source']
            path = safe_path(Path(source_root), source['file'])
            if digest(path) != source['sha256']:
                raise ValueError('reconstruction donor checksum mismatch')
            key = (source['file'], source['sha256'], str(source['select']))
            if key not in cache:
                donor, data = read_glb(path)
                ni = resolve(donor, source['select'])
                node = donor['nodes'][ni]
                if 'skin' in node or 'weights' in node or donor.get('textures'):
                    raise ValueError('reconstruction donor must be rigid and untextured')
                mesh = donor['meshes'][node['mesh']]
                materials, primitives = {}, []
                for p in mesh['primitives']:
                    if p.get('mode', 4) != 4 or 'targets' in p or set(p['attributes']) - {'POSITION', 'NORMAL'}:
                        raise ValueError('unsupported reconstruction donor primitive')
                    old = p.get('material')
                    if old not in materials:
                        materials[old] = len(doc.setdefault('materials', []))
                        doc['materials'].append(copy.deepcopy(donor['materials'][old]) if old is not None else {})
                    points = accessor(donor, data, p['attributes']['POSITION'])
                    normals = accessor(donor, data, p['attributes']['NORMAL']) if 'NORMAL' in p['attributes'] else None
                    indices = accessor(donor, data, p['indices']) if 'indices' in p else np.arange(len(points))
                    used = np.unique(indices)
                    points = points[used]
                    normals = normals[used] if normals is not None else None
                    indices = np.searchsorted(used, indices)
                    primitives.append(primitive(points, normals, indices, materials[old]))
                cache[key] = len(doc['meshes'])
                doc['meshes'].append({'primitives': primitives})
            mi = cache[key]
            provenance['donor'] = source
            provenance['donor_frame'] = 'mesh_local'
        else:
            raise ValueError('unsupported reconstruction type')
        matrix = local_matrix({'matrix': addition.get('matrix', np.eye(4).flatten(order='F').tolist())})
        if not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-6) or np.linalg.det(matrix[:3, :3]) < 0:
            raise ValueError('reconstruction placement must be rigid; scale donor geometry explicitly in a separate asset')
        index = len(doc['nodes'])
        doc['nodes'].append({'name': addition['name'], 'mesh': mi,
                             'matrix': matrix.flatten(order='F').tolist(),
                             'extras': {'reconstruction': provenance}})
        doc['nodes'][parent].setdefault('children', []).append(index)
        meta = copy.deepcopy(addition['metadata'])
        meta['geometry_origin'] = 'reconstruction'
        meta['approximation'] = provenance
        resolved.setdefault('nodes', []).append({'select': {'name': addition['name']},
                                                  'metadata': meta, 'evidence': addition['evidence']})
        for surface in addition.get('surfaces', []):
            entry = copy.deepcopy(surface)
            entry['node_id'] = meta['id']
            entry['metadata']['geometry_origin'] = 'reconstruction'
            entry['metadata']['layer'] = 'reconstruction'
            resolved.setdefault('surfaces', []).append(entry)
    doc['buffers'][0]['byteLength'] = len(payload)
    return doc, bytes(payload), resolved
