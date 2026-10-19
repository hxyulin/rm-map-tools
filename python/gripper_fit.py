# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Fit a two-jaw kinematic grasp to a source unit's axial contact envelope.

This preserves every mesh and uses triangle sections, not just vertex bounds:
long rods can cross the gripping plane without any vertex on that plane.
"""
import numpy as np
from scipy.spatial.transform import Rotation


def section_radius(triangles, heights_m):
    """Largest radial extent where source triangles cross the given z planes."""
    triangles = np.asarray(triangles, float)
    points = []
    for height in heights_m:
        for i, j in [(0, 1), (1, 2), (2, 0)]:
            a, b = triangles[:, i], triangles[:, j]
            valid = ((a[:, 2] - height) * (b[:, 2] - height) <= 0) & (abs(a[:, 2] - b[:, 2]) > 1e-12)
            a, b = a[valid], b[valid]
            u = (height - a[:, 2]) / (b[:, 2] - a[:, 2])
            points.append(a + (b - a) * u[:, None])
        points.append(triangles.reshape(-1, 3)[abs(triangles.reshape(-1, 3)[:, 2] - height) < 1e-12])
    points = np.concatenate(points)
    if not len(points):
        raise ValueError('unit has no source section at the gripping height')
    return float(np.linalg.norm(points[:, :2], axis=1).max())


def pad_radius(triangles, pivot_m, angle_rad):
    """Closest projected source-pad triangle edge to the tool's z axis."""
    moved = (np.asarray(triangles) - pivot_m) @ Rotation.from_rotvec([0, 0, angle_rad]).as_matrix().T + pivot_m
    minimum = float('inf')
    for i, j in [(0, 1), (1, 2), (2, 0)]:
        a, b = moved[:, i, :2], moved[:, j, :2]
        d = b - a
        u = np.clip(-np.sum(a * d, axis=1) / np.maximum(np.sum(d * d, axis=1), 1e-30), 0., 1.)
        minimum = min(minimum, float(np.linalg.norm(a + d * u[:, None], axis=1).min()))
    return minimum


def fit_angle(triangles, pivot_m, open_rad, radius_m):
    """Bisect the source-to-open jaw sweep for a nonpenetrating envelope stop.

    Intended for the reviewed PIE pads, which stay to either side of the axis
    and open monotonically. Reject a contact radius outside that sweep.
    """
    if not pad_radius(triangles, pivot_m, 0.) < radius_m < pad_radius(triangles, pivot_m, open_rad):
        raise ValueError('unit contact envelope is outside the jaw sweep')
    lo, hi = 0., 1.
    for _ in range(50):
        mid = (lo + hi) / 2
        if pad_radius(triangles, pivot_m, open_rad * mid) < radius_m:
            lo = mid
        else:
            hi = mid
    return open_rad * hi
