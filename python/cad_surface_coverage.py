# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Restore source-owned surface pieces omitted by a visual simplification.

Finite material-local sampling detects lost coverage regardless of camera or
occlusion. It is not a continuous Hausdorff or watertightness certificate.
"""
import math
import numpy as np
from cad_component_detail import connected_pieces
from cad_dense_lod import surface_samples
from mesh_quality import distances


def coverage_repair(source_points, source_triangles, points, triangles, *,
                    distance_m=.008, minimum_area_m2=.0001):
    """Return retained candidate faces, restored source faces and a decision ledger.

    All seven samples (corners, edge midpoints, centroid) of every source face
    are checked. A failed connected source piece is restored completely; candidate
    triangles touching it are removed, expanding across bridges between pieces.
    Positions and material boundaries never change. The area threshold is the
    sum of source triangle areas with a failed sample, not exact missing area.
    """
    if not math.isfinite(distance_m) or distance_m <= 0 or not math.isfinite(minimum_area_m2) or minimum_area_m2 < 0:
        raise ValueError('invalid coverage policy')
    p = np.asarray(source_points, float); t = np.asarray(source_triangles)
    q = np.asarray(points, float); f = np.asarray(triangles)
    labels = connected_pieces(p * 1000, t, selection_grid_mm=.0001)
    # The Low exporter retains original vertex positions. Refuse unknown values
    # rather than inferring ownership from proximity across separate surfaces.
    vertex_labels = np.full(len(p), -1, dtype=int)
    vertex_labels[t.ravel()] = np.repeat(labels, 3)
    lookup = {tuple(v): int(label) for v, label in zip(p, vertex_labels) if label >= 0}
    try:
        owners = np.array([lookup[tuple(v)] for v in q[f.ravel()]], int).reshape(-1, 3)
    except KeyError as error:
        raise ValueError('candidate vertex is not source-owned') from error
    delta = distances(surface_samples(p, t).reshape(-1, 3), q, f).reshape(-1, 7).max(1)
    g = p[t]; areas = np.linalg.norm(np.cross(g[:, 1] - g[:, 0], g[:, 2] - g[:, 0]), axis=1) / 2
    selected = set(); records = []
    for label in np.unique(labels):
        mask = labels == label
        bad_area = float(areas[mask & (delta > distance_m)].sum())
        failed = bad_area > minimum_area_m2
        if failed: selected.add(int(label))
        records.append({'piece': int(label), 'source_triangles': int(mask.sum()),
                        'flagged_source_area_m2': bad_area,
                        'maximum_sampled_distance_mm': float(delta[mask].max(initial=0) * 1000),
                        'restored': failed})
    while True:
        touched = np.isin(owners, list(selected)).any(1)
        expanded = set(map(int, owners[touched].ravel()))
        if not expanded <= selected:
            selected.update(expanded)
            continue
        if not selected: break
        restored = np.isin(labels, list(selected))
        candidate = np.concatenate([f[~touched], t[restored] + len(q)])
        # Removing a bridge may uncover a neighboring source surface even when
        # it did not own that bridge's vertices. Recheck until retention closes.
        delta_after = distances(surface_samples(p, t).reshape(-1, 3),
                                np.concatenate([q, p]), candidate).reshape(-1, 7).max(1)
        more = {int(label) for label in np.unique(labels)
                if areas[(labels == label) & (delta_after > distance_m)].sum() > minimum_area_m2}
        if more <= selected: break
        selected.update(more)
    for record in records:
        record['restored'] = record['piece'] in selected
    restore = np.isin(labels, list(selected))
    return ~touched, restore, {'pieces': records, 'restored_pieces': sorted(selected),
                              'distance_m': distance_m, 'minimum_flagged_area_m2': minimum_area_m2}
