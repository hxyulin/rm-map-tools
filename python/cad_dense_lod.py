# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Material-local LOD with every triangle and every corner checked afterward."""
import math
import numpy as np
from cad_local_lod import guarded_vertex_lod
from mesh_quality import distances


def surface_samples(points, triangles):
    """Return seven deterministic samples per triangle, including all corners."""
    g = np.asarray(points)[triangles]
    return np.stack([g[:, 0], g[:, 1], g[:, 2], (g[:, 0] + g[:, 1]) / 2,
                     (g[:, 1] + g[:, 2]) / 2, (g[:, 2] + g[:, 0]) / 2, g.mean(1)], axis=1)


def dense_lod(points_mm, triangles, material_ids, *, nominal_error_mm=1,
              maximum_distance_mm=3, protected_material_ids=(), refinements=3):
    """Simplify one rigid member, locking failing corner neighborhoods on retry.

    Every material is checked against itself, in both directions, using all
    vertices, triangle centroids and edge midpoints. Optical materials can be
    retained exactly. Each retry starts from the same input. This is a finite
    tessellation check, not a continuous native-CAD or opening-clearance proof.
    No materials, disconnected components or motion owners are merged.
    """
    p = np.asarray(points_mm, float); t = np.asarray(triangles); m = np.asarray(material_ids)
    if not all(math.isfinite(v) and v > 0 for v in [nominal_error_mm, maximum_distance_mm]) or type(refinements) is not int or not 1 <= refinements <= 8:
        raise ValueError('invalid dense LOD policy')
    # Let the established backend validate the complete mesh before sampling it.
    protected = np.unique(t[np.isin(m, protected_material_ids)])
    locks = set(map(int, protected)); trials = []; best = (p, t, m); best_count = len(t)
    for _ in range(refinements):
        q, f, k, backend = guarded_vertex_lod(p, t, m, error_mm=nominal_error_mm,
            sampled_limit_mm=maximum_distance_mm * .9, sample_count=max(96, min(262144, len(t))),
            maximum_iterations=16, protected_vertex_indices=np.array(sorted(locks), dtype=np.int64))
        # Locked backend coordinates still pass through a rebased float32 frame.
        # Restore optical triangles from original doubles, including their winding.
        restore = np.isin(m, protected_material_ids)
        if restore.any():
            keep = ~np.isin(k, protected_material_ids)
            f = np.concatenate([f[keep], t[restore] + len(q)])
            k = np.concatenate([k[keep], m[restore]])
            q = np.concatenate([q, p])
        worst = 0.; new_locks = set(); materials = []; optical_exact = True
        for key in np.unique(m):
            old = t[m == key]; new = f[k == key]
            forward = distances(surface_samples(p, old).reshape(-1, 3), q, new).reshape(-1, 7)
            reverse = distances(surface_samples(q, new).reshape(-1, 3), p, old).reshape(-1, 7)
            error = float(max(forward.max(), reverse.max())); worst = max(worst, error)
            bad = old[forward.max(1) > maximum_distance_mm]
            new_locks.update(map(int, bad.ravel()))
            if reverse.max() > maximum_distance_mm:
                from scipy.spatial import cKDTree
                used = np.unique(old); nearest = used[cKDTree(p[used]).query(surface_samples(q, new).reshape(-1, 3)[reverse.ravel() > maximum_distance_mm], k=min(16, len(used)))[1]]
                new_locks.update(map(int, old[np.isin(old, nearest).any(1)].ravel()))
            if key in protected_material_ids:
                optical_exact &= sorted(map(tuple, p[old].reshape(-1, 9))) == sorted(map(tuple, q[new].reshape(-1, 9)))
            materials.append({'material_id': int(key), 'input_triangles': len(old), 'output_triangles': len(new), 'maximum_sampled_distance_mm': error})
        accepted = worst <= maximum_distance_mm and optical_exact
        trials.append({'triangles': len(f), 'locked_vertices': len(locks), 'maximum_sampled_distance_mm': worst, 'protected_materials_exact': optical_exact, 'accepted': accepted, 'materials': materials})
        if accepted and len(f) < best_count: best = (q, f, k); best_count = len(f)
        if accepted: break
        before = len(locks); locks.update(new_locks)
        if before == len(locks): break
    q, f, k = best
    return q, f, k, {'pass': 'dense-material-corner-lod-v1', 'input_triangles': len(t), 'output_triangles': len(f), 'nominal_error_mm': nominal_error_mm,
        'maximum_distance_mm': maximum_distance_mm, 'protected_material_ids': list(map(int, protected_material_ids)), 'trials': trials,
        'retained_input': best_count == len(t), 'scope': 'Seven samples per triangle in both directions, per material; exact optical regions. Finite tessellation guard, not continuous CAD equivalence or clearance certification.'}
