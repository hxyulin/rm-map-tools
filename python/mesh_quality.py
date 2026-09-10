# SPDX-License-Identifier: MIT OR Apache-2.0
"""Deterministic sampled point-to-triangle deviations; not a Hausdorff proof."""
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray


def nondegenerate(points, triangles):
    v = points[triangles]
    area = np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1)
    return triangles[area > 1e-20]


def sample_points(points, triangles, count=96):
    triangles = nondegenerate(points, triangles)
    if not len(triangles):
        return np.empty((0, 3))
    selected = triangles[np.linspace(0, len(triangles) - 1, min(count, len(triangles)), dtype=int)]
    p = points[selected]
    return np.vstack([p.mean(axis=1), p[:, 0], (p[:, 0] + p[:, 1]) / 2])


def distances(samples, points, triangles):
    triangles = nondegenerate(points, triangles)
    if not len(samples):
        return np.empty(0)
    if not len(triangles):
        return np.full(len(samples), np.inf)
    pts = vtk.vtkPoints()
    pts.SetData(numpy_to_vtk(np.ascontiguousarray(points, dtype=np.float64), deep=True))
    cells = vtk.vtkCellArray()
    packed = np.column_stack([np.full(len(triangles), 3), triangles]).astype(np.int64)
    cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(packed.ravel(), deep=True))
    poly = vtk.vtkPolyData()
    poly.SetPoints(pts)
    poly.SetPolys(cells)
    locator = vtk.vtkStaticCellLocator()
    locator.SetDataSet(poly)
    locator.BuildLocator()
    closest = [0., 0., 0.]
    cell, sub, dist2 = vtk.reference(0), vtk.reference(0), vtk.reference(0.)
    result = []
    for p in samples:
        locator.FindClosestPoint(p, closest, cell, sub, dist2)
        result.append(float(dist2) ** .5)
    return np.asarray(result)


def deviation(before_points, before_triangles, after_points, after_triangles, count=96):
    values = np.concatenate([
        distances(sample_points(before_points, before_triangles, count), after_points, after_triangles),
        distances(sample_points(after_points, after_triangles, count), before_points, before_triangles),
    ])
    return {'sample_count': len(values), 'max': float(values.max()) if len(values) else 0,
            'p99': float(np.percentile(values, 99)) if len(values) else 0}
