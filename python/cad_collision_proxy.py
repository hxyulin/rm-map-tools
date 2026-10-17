# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Collision-only reductions within one caller-owned rigid source member.

Appearance seams have no collision meaning. Boundary vertices and disconnected
components remain constrained; closed, nearly box-shaped members can become a
12-triangle primitive. This does not select scenery or replace scoring targets.
"""
import math
import numpy as np


def collision_proxy(points_mm, triangles, *, sampled_limit_mm=3,
                    nominal_error_mm=1, sample_count=8192, box_grid_mm=3):
    """Try a checked box, otherwise reduce an unpainted collision tessellation.

    Call once per rigid native member, never on a whole equipment assembly.
    A box requires a closed orientable input, volume agreement within 2%, and
    dense surface checks in both directions. Open or hollow members fall back
    to a component-retaining, boundary-locked reducer. The returned optional
    ``primitive`` describes a future physics box, not an installed collider.
    All deviation statements are finite sample checks, not continuous bounds.
    """
    from cad_local_lod import guarded_vertex_lod
    from mesh_quality import distances, sample_points, deviation
    p = np.asarray(points_mm, float); t = np.asarray(triangles)
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all() or t.ndim != 2 or t.shape[1] != 3 or not np.issubdtype(t.dtype, np.integer) or not len(t) or t.min() < 0 or t.max() >= len(p): raise ValueError('invalid collision mesh')
    if not all(math.isfinite(v) and v > 0 for v in [sampled_limit_mm, nominal_error_mm, box_grid_mm]) or type(sample_count) is not int or not 96 <= sample_count <= 16384: raise ValueError('invalid collision policy')
    # Ignore material seams, but never weld nearby independent surfaces.
    p, inverse = np.unique(p[t].reshape(-1, 3), axis=0, return_inverse=True); t = inverse.reshape(-1, 3)
    edges = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    keys, counts = np.unique(np.sort(edges, axis=1), axis=0, return_counts=True)
    border = np.unique(keys[counts == 1]); box_trials = []
    closed = bool(np.all(counts == 2))
    # A winding check avoids treating doubled, coincident plates as a volume.
    direction = np.where(edges[:, 0] < edges[:, 1], 1, -1)
    _, indices = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True)
    closed = closed and bool(np.all(np.bincount(indices, weights=direction) == 0))
    origin = (p.min(0) + p.max(0)) / 2
    centered = p - origin
    source_volume = abs(float(np.einsum('ij,ij->i', centered[t[:, 0]], np.cross(centered[t[:, 1]], centered[t[:, 2]])).sum() / 6))
    if closed and len(t) > 12 and source_volume > 1e-6:
        _, _, axes = np.linalg.svd(centered, full_matrices=False)
        if np.linalg.det(axes) < 0: axes[-1] *= -1
        for frame in [np.eye(3), axes]:
            local = centered @ frame.T; lo, hi = local.min(0), local.max(0); span = hi - lo
            box_volume = float(np.prod(span))
            if span.min() < .01 or abs(box_volume - source_volume) > .02 * source_volume:
                box_trials.append({'accepted': False, 'reason': 'box volume differs by more than 2%'}); continue
            q = np.array([[x, y, z] for x in [lo[0], hi[0]] for y in [lo[1], hi[1]] for z in [lo[2], hi[2]]])
            f = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
            q = q @ frame + origin
            # Grid every box face; sparse triangle-centroid checks alone could
            # overlook the center of a broad window in a thin plate.
            grids = []
            for axis in range(3):
                a, b = [k for k in range(3) if k != axis]
                na, nb = np.ceil(span[[a, b]] / min(box_grid_mm, sampled_limit_mm)).astype(int) + 1
                if na * nb > 100000: break
                aa, bb = np.meshgrid(np.linspace(lo[a], hi[a], na), np.linspace(lo[b], hi[b], nb))
                for level in [lo[axis], hi[axis]]:
                    grid = np.empty((aa.size, 3)); grid[:, axis] = level; grid[:, a] = aa.ravel(); grid[:, b] = bb.ravel(); grids.append(grid @ frame + origin)
            else:
                forward = distances(np.concatenate([p, sample_points(p, t, sample_count)]), q, f)
                reverse = distances(np.concatenate(grids), p, t)
                worst = float(max(forward.max(), reverse.max()))
                accepted = worst <= sampled_limit_mm
                box_trials.append({'accepted': accepted, 'maximum_sampled_deviation_mm': worst, 'surface_grid_samples': sum(len(g) for g in grids), 'source_volume_mm3': source_volume, 'box_volume_mm3': box_volume})
                if accepted:
                    center = ((lo + hi) / 2) @ frame + origin
                    return q, f, {'pass': 'rigid-member-collision-proxy-v1', 'operation': 'box', 'input_triangles': len(t), 'output_triangles': 12, 'sampled_limit_mm': sampled_limit_mm,
                                  'primitive': {'kind': 'box', 'center_mm': center.tolist(), 'half_extents_mm': (span / 2).tolist(), 'axes': frame.tolist()}, 'box_trials': box_trials}
                continue
            box_trials.append({'accepted': False, 'reason': 'dense box grid exceeds bounded sample budget'})
    q, f, _, guard = guarded_vertex_lod(p, t, np.zeros(len(t), dtype=np.int64), error_mm=nominal_error_mm,
                                       sampled_limit_mm=sampled_limit_mm, sample_count=sample_count,
                                       maximum_iterations=8, protected_vertex_indices=border)
    check = deviation(p, t, q, f, count=max(len(t), len(f)))
    if check['max'] > sampled_limit_mm or len(f) > len(t): q, f = p, t
    # Locked border coordinates use a rebased float32 reducer frame. Restore
    # their original doubles before exporting an independent collision asset.
    if len(border):
        from scipy.spatial import cKDTree
        distance, nearest = cKDTree(q).query(p[border])
        if np.any(distance > .001) or len(np.unique(nearest)) != len(border): q, f = p.copy(), t
        else: q[nearest] = p[border]
    check = deviation(p, t, q, f, count=max(len(t), len(f)))
    if check['max'] > sampled_limit_mm: q, f = p, t; check = deviation(p, t, q, f, count=len(t))
    return q, f, {'pass': 'rigid-member-collision-proxy-v1', 'operation': 'unpainted-boundary-locked-lod',
                  'input_triangles': len(t), 'output_triangles': len(f), 'primitive': None,
                  'sampled_limit_mm': sampled_limit_mm, 'sampled_deviation_mm': check,
                  'locked_boundary_vertices': len(border), 'box_trials': box_trials, 'guard': guard}
