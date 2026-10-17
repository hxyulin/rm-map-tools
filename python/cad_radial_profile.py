# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Fit an explicitly selected star-shaped exterior to radial section profiles.

This is an approximate visual envelope. It intentionally omits radially hidden
surfaces, cannot represent arbitrary undercuts and is never a collision policy.
"""
import math
import numpy as np


def radial_samples(points_mm, triangles, material_ids, *, heights_mm, angles_rad,
                   axis=1, centre_mm=(0, 0, 0)):
    """Sample first outward-visible source intersections along inward radial rays.

    Output radii and source material IDs are height-by-angle arrays. Missing
    intersections reject the proposed envelope rather than bridging empty space.
    The caller owns source selection, axial end planes and semantic admission.
    """
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    p = np.asarray(points_mm, float); t = np.asarray(triangles)
    m = np.asarray(material_ids); heights = np.asarray(heights_mm, float)
    angles = np.asarray(angles_rad, float); centre = np.asarray(centre_mm, float)
    if axis not in (0, 1, 2) or p.ndim != 2 or p.shape[1] != 3 or t.ndim != 2 or t.shape[1] != 3 or not len(t) or not np.issubdtype(t.dtype, np.integer) or t.min() < 0 or t.max() >= len(p) or m.shape != (len(t),) or centre.shape != (3,) or not all(np.isfinite(a).all() for a in [p, heights, angles, centre]) or not len(heights) or not len(angles):
        raise ValueError('invalid radial source mesh or sampling frame')
    radial_axes = [a for a in range(3) if a != axis]
    radius = np.linalg.norm((p - centre)[:, radial_axes], axis=1).max() + 1
    data = vtk.vtkPolyData(); vp = vtk.vtkPoints(); vp.SetData(numpy_to_vtk(p, deep=True)); data.SetPoints(vp)
    cells = vtk.vtkCellArray(); packed = np.c_[np.full(len(t), 3), t].astype(np.int64)
    cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(packed.ravel(), deep=True)); data.SetPolys(cells)
    locator = vtk.vtkStaticCellLocator(); locator.SetDataSet(data); locator.BuildLocator()
    radii = np.empty((len(heights), len(angles))); materials = np.empty(radii.shape, dtype=m.dtype)
    hit = [0., 0., 0.]; pc = [0., 0., 0.]; param = vtk.reference(0.); sub = vtk.reference(0); cell = vtk.reference(0)
    for j, height in enumerate(heights):
        end = centre.copy(); end[axis] = height
        for k, angle in enumerate(angles):
            direction = np.zeros(3); direction[radial_axes] = [math.cos(angle), math.sin(angle)]
            start = end + radius * direction
            if not locator.IntersectWithLine(start, end, 1e-8, param, hit, pc, sub, cell):
                raise ValueError(f'non-star-shaped or empty radial section at {height} mm / {angle} rad')
            radii[j, k] = np.linalg.norm((np.asarray(hit) - end)[radial_axes])
            materials[j, k] = m[int(cell)]
    return radii, materials


def select_profile_rows(heights_mm, radii_mm, material_ids, *, tolerance_mm=.2):
    """Keep shared axial knots with bounded sampled radial chord error.

    Every observed source material transition keeps both adjacent rows. This is
    a bound on the supplied radial samples, not a continuous source-surface bound.
    """
    h = np.asarray(heights_mm, float); r = np.asarray(radii_mm, float); m = np.asarray(material_ids)
    if h.ndim != 1 or len(h) < 2 or r.ndim != 2 or r.shape[0] != len(h) or m.shape != r.shape or np.any(np.diff(h) <= 0) or not np.isfinite(h).all() or not np.isfinite(r).all() or np.any(r <= 0) or not math.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError('invalid sampled radial profile')
    retained = {0, len(h) - 1}
    changes = np.flatnonzero(np.any(m[1:] != m[:-1], axis=1))
    retained.update(map(int, changes)); retained.update(map(int, changes + 1))
    def split(a, b):
        if b <= a + 1: return
        fraction = (h[a + 1:b] - h[a]) / (h[b] - h[a])
        estimate = r[a] + fraction[:, None] * (r[b] - r[a])
        errors = np.max(abs(r[a + 1:b] - estimate), axis=1); index = int(errors.argmax())
        if errors[index] > tolerance_mm:
            mid = a + 1 + index; retained.add(mid); split(a, mid); split(mid, b)
    mandatory = sorted(retained)
    for a, b in zip(mandatory, mandatory[1:]): split(a, b)
    return np.array(sorted(retained), dtype=np.int64)


def profile_mesh(heights_mm, angles_rad, radii_mm, side_material_ids, *, axis=1,
                 centre_mm=(0, 0, 0), cap_material_ids=(0, 0)):
    """Create shared radial rings, two triangles per side quad and end-cap fans.

    Winding is outward and all rings use the same angles, so there are no cracks
    at profile or material seams. Cap colors require explicit caller selection.
    """
    h = np.asarray(heights_mm, float); a = np.asarray(angles_rad, float); r = np.asarray(radii_mm, float)
    m = np.asarray(side_material_ids); centre = np.asarray(centre_mm, float)
    if axis not in (0, 1, 2) or len(h) < 2 or len(a) < 3 or r.shape != (len(h), len(a)) or m.shape != (len(h) - 1, len(a)) or np.any(np.diff(h) <= 0) or np.any(np.diff(a) <= 0) or a[-1] - a[0] >= 2 * math.pi or np.any(r <= 0) or centre.shape != (3,) or len(cap_material_ids) != 2 or not all(np.isfinite(v).all() for v in [h, a, r, centre]):
        raise ValueError('invalid radial mesh profile')
    radial_axes = [v for v in range(3) if v != axis]
    p = np.tile(centre, (len(h), len(a), 1)); p[:, :, axis] = h[:, None]
    p[:, :, radial_axes[0]] += r * np.cos(a); p[:, :, radial_axes[1]] += r * np.sin(a)
    p = p.reshape(-1, 3); triangles = []; materials = []; n = len(a)
    for j in range(len(h) - 1):
        for k in range(n):
            v, w = j * n + k, j * n + (k + 1) % n
            triangles.extend([[v, w, w + n], [v, w + n, v + n]])
            materials.extend([int(m[j, k])] * 2)
    for end, row in enumerate([0, len(h) - 1]):
        c = centre.copy(); c[axis] = h[row]; ci = len(p); p = np.vstack([p, c])
        for k in range(n):
            tri = [ci, row * n + (k + 1) % n, row * n + k]
            triangles.append(tri if end == 0 else tri[::-1]); materials.append(int(cap_material_ids[end]))
    t = np.array(triangles, dtype=np.int64)
    # The X/Z radial frame is left handed around Y; correct its entire winding.
    if axis == 1: t = t[:, ::-1]
    return p, t, np.array(materials, dtype=np.int64)


def clip_below(points_mm, triangles, material_ids, *, axis, height_mm):
    """Clip a mesh to an axial half-space, retaining winding and per-face color.

    Fully retained triangles stay exact. New cut vertices interpolate only their
    source triangle edges; no cap is invented and no surface is moved.
    """
    p = np.asarray(points_mm, float); t = np.asarray(triangles); m = np.asarray(material_ids)
    if axis not in (0, 1, 2) or not math.isfinite(height_mm) or m.shape != (len(t),):
        raise ValueError('invalid clipping plane')
    result = []; colors = []; owners = []
    for index, tri in enumerate(t):
        polygon = p[tri]; clipped = []
        for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
            inside_a = a[axis] <= height_mm; inside_b = b[axis] <= height_mm
            if inside_a: clipped.append(a)
            if inside_a != inside_b:
                cut = a + (b - a) * ((height_mm - a[axis]) / (b[axis] - a[axis]))
                cut[axis] = height_mm; clipped.append(cut)
        for j in range(1, len(clipped) - 1):
            g = np.array([clipped[0], clipped[j], clipped[j + 1]])
            if np.linalg.norm(np.cross(g[1] - g[0], g[2] - g[0])) <= 1e-12: continue
            result.append(g); colors.append(m[index]); owners.append(index)
    g = np.array(result).reshape(-1, 3, 3)
    return g.reshape(-1, 3), np.arange(len(g) * 3).reshape(-1, 3), np.array(colors, dtype=m.dtype), np.array(owners, dtype=np.int64)
