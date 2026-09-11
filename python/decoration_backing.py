# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reviewed centre-deck symbol sidewalls and their flat collision backing."""
import copy
import hashlib
from collections import Counter

import numpy as np
from gltf_scene import accessor
from simplify_package import append_accessor


def geometry(doc, binary, primitive):
    return (accessor(doc, binary, primitive['attributes']['POSITION']),
            accessor(doc, binary, primitive['indices']).reshape(-1, 3))


def fingerprint(doc, binary, primitive):
    p, t = geometry(doc, binary, primitive)
    return hashlib.sha256(p.tobytes() + t.tobytes()).hexdigest()


def flat_backing(triangles):
    """Cancel shared edges, then triangulate only the remaining deck boundary."""
    import vtk
    # CAD float32 copies differ by under a micrometre at shared vertices.
    vertices, inverse = np.unique(np.round(triangles.reshape(-1, 3), 6), axis=0, return_inverse=True)
    indices = inverse.reshape(-1, 3)
    counts = Counter(tuple(sorted(edge)) for t in indices for edge in
                     [(t[0], t[1]), (t[1], t[2]), (t[2], t[0])])
    if any(n > 2 for n in counts.values()):
        raise ValueError('nonmanifold deck')
    edges = [edge for edge, count in counts.items() if count == 1]
    degree = Counter(v for edge in edges for v in edge)
    if not edges or any(n != 2 for n in degree.values()):
        raise ValueError('deck boundary is not closed')
    points = vtk.vtkPoints()
    points.SetDataTypeToDouble()
    for p in vertices:
        points.InsertNextPoint(*p)
    lines = vtk.vtkCellArray()
    for a, b in edges:
        lines.InsertNextCell(2)
        lines.InsertCellPoint(a)
        lines.InsertCellPoint(b)
    poly = vtk.vtkPolyData()
    poly.SetPoints(points)
    poly.SetLines(lines)
    triangulator = vtk.vtkContourTriangulator()
    triangulator.SetInputData(poly)
    triangulator.Update()
    if triangulator.GetTriangulationError():
        raise ValueError('deck triangulation failed')
    out = triangulator.GetOutput()
    cells = []
    for i in range(out.GetNumberOfCells()):
        cell = out.GetCell(i)
        if cell.GetNumberOfPoints() != 3:
            raise ValueError('non-triangle deck output')
        cells.append([out.GetPoint(cell.GetPointId(j)) for j in range(3)])
    result = np.asarray(cells)
    def area(t):
        return np.linalg.norm(np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]), axis=1).sum()/2
    if not np.isclose(area(triangles), area(result), rtol=1e-6, atol=1e-8):
        raise ValueError('deck coverage changed')
    return result


def repair(visual, vb, collision, cb, spec):
    vd, cd = copy.deepcopy(visual), copy.deepcopy(collision)
    payloads = [bytearray(vb), bytearray(cb)]
    nodes = []
    for doc in (vd, cd):
        matches = [n for n in doc['nodes'] if n.get('name') == spec['node']]
        if len(matches) != 1:
            raise ValueError('missing/ambiguous backing node')
        node = matches[0]
        mesh = copy.deepcopy(doc['meshes'][node['mesh']])
        node['mesh'] = len(doc['meshes'])
        doc['meshes'].append(mesh)
        nodes.append((node, mesh))
    def primitive(doc, mesh, material):
        matches = [p for p in mesh['primitives'] if doc['materials'][p['material']]['name'] == material]
        if len(matches) != 1:
            raise ValueError('missing/ambiguous backing material')
        return matches[0]
    vcap = primitive(vd, nodes[0][1], spec['cap_material'])
    if fingerprint(vd, vb, vcap) != spec['cap_geometry_sha256']:
        raise ValueError('symbol cap geometry changed; review required')
    vp, vt = geometry(vd, vb, vcap)
    caps = vp[vt].copy()
    base = spec['deck_height_m']
    if np.max(abs(caps[:, :, 2] - base - .001)) > 1e-6:
        raise ValueError('symbol relief height changed')
    caps[:, :, 2] = base
    removed = []
    for k, (doc, binary, (node, mesh)) in enumerate(zip((vd, cd), (vb, cb), nodes)):
        gray = primitive(doc, mesh, spec['side_material'])
        if fingerprint(doc, binary, gray) != spec['side_geometry_sha256']:
            raise ValueError('symbol sidewall geometry changed; review required')
        p, t = geometry(doc, binary, gray)
        mask = np.zeros(len(t), bool)
        for lo, hi in spec['side_triangle_ranges']:
            if not 0 <= lo < hi <= len(t) or mask[lo:hi].any():
                raise ValueError('invalid sidewall partition')
            mask[lo:hi] = True
        if int(mask.sum()) != 288:
            raise ValueError('expected both reviewed symbol skirts')
        def indexed(pr, triangles):
            out = copy.deepcopy(pr)
            out['indices'] = append_accessor(doc, payloads[k], np.asarray(triangles, dtype='<u4').ravel(), 'SCALAR', 5125)
            return out
        retained = indexed(gray, t[~mask])
        gray.update(retained)
        if k == 0:
            decoration = indexed(gray, t[mask])
            decoration['extras'] = {'rm': {'layer': 'decoration', 'kind': 'symbol', 'roles': ['decoration'], 'collision': False}}
            node.setdefault('children', []).append(len(doc['nodes']))
            doc['nodes'].append(dict(name=spec['node']+'/symbol-sidewalls', mesh=len(doc['meshes']),
                                    extras=copy.deepcopy(decoration['extras'])))
            doc['meshes'].append(dict(primitives=[decoration]))
        else:
            dark = primitive(doc, mesh, spec['deck_material'])
            if fingerprint(doc, binary, dark) != spec['deck_geometry_sha256']:
                raise ValueError('deck geometry changed; review required')
            p, t = geometry(doc, binary, dark)
            top = np.max(abs(p[t, 2]-base), axis=1) < 1e-6
            if int(top.sum()) != 156:
                raise ValueError('deck top selection changed')
            restored = flat_backing(np.concatenate([p[t[top]], caps]))
            combined = np.concatenate([p[t[~top]], restored]).astype('<f4')
            flat = combined.reshape(-1, 3)
            normals = np.cross(combined[:, 1]-combined[:, 0], combined[:, 2]-combined[:, 0])
            lengths = np.linalg.norm(normals, axis=1)
            normals /= np.maximum(lengths[:, None], 1e-30)
            dark['attributes'] = dict(POSITION=append_accessor(doc, payloads[k], flat, 'VEC3', 5126),
                NORMAL=append_accessor(doc, payloads[k], np.repeat(normals, 3, axis=0).astype('<f4'), 'VEC3', 5126))
            dark['indices'] = append_accessor(doc, payloads[k], np.arange(len(flat), dtype='<u4'), 'SCALAR', 5125)
            removed = dict(sidewall_triangles=288, old_deck_triangles=156,
                           restored_deck_triangles=len(restored), deck_height_m=base,
                           boundary_weld_m=0.000001)
        doc['buffers'][0]['byteLength'] = len(payloads[k])
    return vd, bytes(payloads[0]), cd, bytes(payloads[1]), removed
