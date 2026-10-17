# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Repair budget LOD by guarding separate pieces and their material surfaces."""
import math
import numpy as np
import meshoptimizer as mo
from cad_component_detail import connected_pieces
from cad_dense_lod import surface_samples
from cad_experimental_lod import coarse_indices
from mesh_quality import distances


def repaired_indices(points, triangles, *, ratio=.1, maximum_distance_mm=4,
                     allowed_bad_area_fraction=.02):
    """Keep cheap clusters that pass; retry failed pieces with indexed collapses.

    Checks cover all triangle corners, edge midpoints and centroids in both
    directions inside one connected material piece. A limited area fraction may
    exceed the distance threshold, permitting recessed micro-detail to vanish.
    Source/candidate axis extents must remain within the same distance threshold.
    Positional welding is used only to select edge
    collapses; returned indices still address exact original vertex values.
    Small texture/optical policies belong to the caller. Finite samples are not
    a continuous surface, aperture or assembled light-occlusion guarantee.
    """
    if not math.isfinite(maximum_distance_mm) or maximum_distance_mm <= 0:
        raise ValueError('invalid surface guard')
    if not math.isfinite(allowed_bad_area_fraction) or not 0 <= allowed_bad_area_fraction < 1:
        raise ValueError('invalid area policy')
    # Established selector validates ratio and mesh before splitting.
    p = np.asarray(points, float); t = np.asarray(triangles)
    coarse_indices(p, t, ratio)
    labels = connected_pieces(p * 1000, t, selection_grid_mm=.0001)
    output = []; records = []
    for label in np.unique(labels):
        old = t[labels == label]; used, inv = np.unique(old, return_inverse=True)
        local = p[used]; original = inv.reshape(-1, 3)
        source_samples = surface_samples(local * 1000, original).reshape(-1, 3)
        def areas(f):
            g = local[f]
            return np.linalg.norm(np.cross(g[:, 1] - g[:, 0], g[:, 2] - g[:, 0]), axis=1)
        source_area = areas(original)
        _, first_welded, welded = np.unique(np.round((local - local.min(0)) * 1e7).astype(np.int64), axis=0, return_index=True, return_inverse=True)
        def edges_and_counts(f):
            w = welded[f]
            edges = np.sort(np.concatenate([w[:, [0, 1]], w[:, [1, 2]], w[:, [2, 0]]]), axis=1)
            edges = edges[edges[:, 0] != edges[:, 1]]
            return np.unique(edges, axis=0, return_counts=True)
        source_edges, source_counts = edges_and_counts(original)
        source_closed = bool(np.all(source_counts == 2))
        source_lines = local[first_welded[source_edges[source_counts == 1]]] * 1000
        def boundary_error(f):
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            edges, counts = edges_and_counts(f)
            boundary = edges[counts == 1]
            if not len(boundary): return 0.
            if not len(source_lines): return float('inf')
            # Each remaining open loop must anchor to an existing source wire.
            # We do not require every curved boundary chord to match the native
            # wire: that would restore excessive detail at this visual LOD.
            used_boundary, inv = np.unique(boundary, return_inverse=True)
            boundary_edges = inv.reshape(-1, 2)
            _, components = connected_components(coo_matrix((np.ones(len(boundary_edges)),
                (boundary_edges[:, 0], boundary_edges[:, 1])), shape=(len(used_boundary),) * 2).tocsr(), directed=False)
            queries = local[first_welded[used_boundary]] * 1000
            a = source_lines[:, 0]; vector = source_lines[:, 1] - a
            length = np.maximum(np.sum(vector * vector, axis=1), 1e-30)
            values = []
            for start in range(0, len(queries), 128):
                delta = queries[start:start + 128, None, :] - a
                along = np.clip(np.sum(delta * vector, axis=2) / length, 0, 1)
                squared = np.sum((delta - along[:, :, None] * vector) ** 2, axis=2)
                values.extend(np.sqrt(squared.min(1)).tolist())
            values = np.array(values)
            return max(float(values[components == c].min()) for c in np.unique(components))
        def measure(f):
            forward = distances(source_samples, local * 1000, f).reshape(-1, 7)
            reverse = distances(surface_samples(local * 1000, f).reshape(-1, 3), local * 1000, original).reshape(-1, 7)
            target_area = areas(f)
            bad = max(float(source_area[forward.max(1) > maximum_distance_mm].sum() / max(source_area.sum(), 1e-30)),
                      float(target_area[reverse.max(1) > maximum_distance_mm].sum() / max(target_area.sum(), 1e-30)))
            before = local[original].reshape(-1, 3); after = local[f].reshape(-1, 3)
            bounds = float(max(abs(before.min(0) - after.min(0)).max(), abs(before.max(0) - after.max(0)).max()) * 1000)
            edges, counts = edges_and_counts(f)
            closed = bool(np.all(counts == 2))
            wire_error = boundary_error(f)
            if not math.isfinite(wire_error): wire_error = None
            return float(max(forward.max(initial=0), reverse.max(initial=0))), bad, bounds, (not source_closed or closed), wire_error
        def accepted(measured): return measured[1] <= allowed_bad_area_fraction and measured[2] <= maximum_distance_mm and measured[3] and measured[4] is not None and measured[4] <= min(1., maximum_distance_mm)
        f = coarse_indices(local, original, ratio); measured = measure(f); method = 'cluster'
        trials = [{'method': method, 'triangles': len(f), 'measurements': measured}]
        if not accepted(measured):
            # Restore budget only in failing pieces. A few more representatives
            # can recover a rim or a sheet without retaining its CAD topology.
            for budget in [.15, .225, .35, .55, .75]:
                if budget <= ratio: continue
                f = coarse_indices(local, original, budget); measured = measure(f)
                trials.append({'method': 'cluster-refinement', 'ratio': budget,
                               'triangles': len(f), 'measurements': measured})
                if accepted(measured):
                    method = 'cluster-refinement'; break
        if not accepted(measured):
            # Topology-aware collapses on welded source positions avoid the
            # holes caused by unconstrained clustering of broad flat panels.
            xyz = np.ascontiguousarray(local - (local.min(0) + local.max(0)) / 2, dtype=np.float32)
            q, first, inverse = np.unique(xyz, axis=0, return_index=True, return_inverse=True)
            indices = np.ascontiguousarray(inverse[original].ravel(), dtype=np.uint32)
            buffer = np.empty_like(indices)
            for fraction in [1, .25, .0625]:
                count = mo.simplify(buffer, indices, q,
                    target_index_count=max(3, 3 * math.ceil(len(original) * ratio)),
                    target_error=maximum_distance_mm / 1000 * fraction,
                    options=mo.SIMPLIFY_ERROR_ABSOLUTE)
                if not count: continue
                f = first[buffer[:count].reshape(-1, 3)]; measured = measure(f); method = 'welded-collapse'
                trials.append({'method': method, 'error_fraction': fraction, 'triangles': len(f), 'measurements': measured})
                if accepted(measured): break
            if not accepted(measured):
                f = original; measured = (0., 0., 0., True, 0.); method = 'retain-source'
        output.append(used[f]); records.append({'piece': int(label), 'input': len(old),
            'output': len(f), 'method': method, 'maximum_sampled_distance_mm': measured[0],
            'bad_surface_area_fraction': measured[1], 'bounds_deviation_mm': measured[2],
            'source_closed': source_closed, 'closure_retained': measured[3],
            'maximum_boundary_loop_anchor_distance_mm': measured[4], 'trials': trials})
    return np.concatenate(output), {'pieces': records, 'maximum_distance_mm': maximum_distance_mm,
                                   'allowed_bad_area_fraction': allowed_bad_area_fraction,
                                   'maximum_sampled_distance_mm': max(r['maximum_sampled_distance_mm'] for r in records)}


def visual_selector(points, triangles, material, primitive, *, structural_distance_mm=4,
                    chromatic_distance_mm=.5, allowed_bad_area_fraction=.02):
    """Use a tighter 0.5 mm guard for saturated paint/lights; retain artwork UVs.

    Saturation is a conservative appearance policy, not inferred semantic LED
    ownership. Nonchromatic surfaces use a 4 mm guard. Textured primitives keep
    original topology to preserve UV seams and source artwork completely.
    """
    pbr = material.get('pbrMetallicRoughness', {})
    if any('Texture' in key for key in pbr) or 'normalTexture' in material:
        return triangles.copy(), {'policy': 'retain-textured', 'maximum_sampled_distance_mm': 0}
    color = material.get('extras', {}).get('step_colour_srgb')
    if color is None: color = pbr.get('baseColorFactor', [.6, .6, .6, 1])[:3]
    chromatic = max(color) - min(color) > .15
    limit = chromatic_distance_mm if chromatic else structural_distance_mm
    f, report = repaired_indices(points, triangles, maximum_distance_mm=limit,
                                allowed_bad_area_fraction=allowed_bad_area_fraction)
    report['policy'] = ('chromatic-' if chromatic else 'structural-') + str(limit) + 'mm'
    return f, report


def selective_indices(points, triangles, material, primitive, selected_pieces, *, exact_pieces=(),
                      source_patch_triangles=(), **policy):
    """Refine only named pieces, preserving the original Low elsewhere.

    Names are positional connectivity labels within one source material primitive.
    A candidate triangle spanning multiple pieces expands the repair set to all
    its owners before replacement, avoiding partial bridges into unrefined pieces.
    Caller must qualify selection; camera visibility here never deletes a piece.
    """
    p = np.asarray(points); t = np.asarray(triangles)
    low = coarse_indices(p, t, .1)
    patch = np.asarray(source_patch_triangles, dtype=np.int64)
    if patch.ndim != 1 or (len(patch) and (patch.min() < 0 or patch.max() >= len(t))): raise ValueError('invalid source patch triangles')
    def with_patches(f):
        if not len(patch): return f
        result = np.concatenate([f, t[patch]])
        _, position_ids = np.unique(p, axis=0, return_inverse=True)
        keys = position_ids[result]; start = np.argmin(keys, axis=1)
        keys = np.take_along_axis(keys, (start[:, None] + np.arange(3)) % 3, axis=1)
        _, first = np.unique(keys, axis=0, return_index=True)
        return result[np.sort(first)]
    if not selected_pieces and not exact_pieces:
        return with_patches(low), {'policy': 'retain-original-low', 'selected_pieces': [], 'source_patch_triangles': patch.tolist()}
    labels = connected_pieces(p * 1000, t, selection_grid_mm=.0001)
    exact = set(map(int, exact_pieces)); selected = set(map(int, selected_pieces)) | exact
    if not selected <= set(map(int, np.unique(labels))): raise ValueError('unknown selected piece')
    vertex_labels = np.zeros(len(p), int); vertex_labels[t.ravel()] = np.repeat(labels, 3)
    owners = vertex_labels[low]
    while True:
        touched = np.isin(owners, list(selected)).any(1)
        more = set(map(int, owners[touched].ravel()))
        if more <= selected: break
        selected.update(more)
    output = [low[~touched]]; records = []
    for label in sorted(selected):
        if label in exact:
            f = t[labels == label]; record = {'policy': 'retain-source-interior-gap', 'maximum_sampled_distance_mm': 0}
        else:
            f, record = visual_selector(p, t[labels == label], material, primitive, **policy)
        output.append(f); records.append({'source_piece': label, **record})
    return with_patches(np.concatenate(output)), {'policy': 'selective-visible-repair',
        'selected_pieces': sorted(selected), 'repairs': records, 'source_patch_triangles': patch.tolist()}
