# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Rebuild structural planar domains from source triangles across mesh seams.

Callers supply one rigid owner and one appearance. Holes/disconnected polygons
come from polygon union, never a convex hull. Units are millimetres.
"""
from collections import defaultdict
import math
import numpy as np


def rebuild_panels(source, candidate, *, plane_tolerance_mm=.02,
                   boundary_tolerance_mm=.05, minimum_area_mm2=100,
                   minimum_source_triangles=6):
    """Return kept candidate indices and newly triangulated source panels.

    Source plane grouping is a discovery heuristic. Every accepted group has a
    complete vertex-to-plane check, projected boundary/area checks, retained
    polygon/hole counts and a triangulated-domain equality check. This does not
    certify curved remainder coverage, contacts or complete solid topology.
    """
    import shapely as sh
    source = np.asarray(source, float)
    candidate = np.asarray(candidate, float)
    for mesh in (source, candidate):
        if mesh.ndim != 3 or mesh.shape[1:] != (3, 3) or not np.isfinite(mesh).all():
            raise ValueError('expected finite triangle positions')
    if not all(math.isfinite(v) and v > 0 for v in (plane_tolerance_mm, boundary_tolerance_mm, minimum_area_mm2)) or minimum_source_triangles < 2:
        raise ValueError('invalid planar policy')
    def planes(g):
        normal = np.cross(g[:, 1] - g[:, 0], g[:, 2] - g[:, 0])
        norm = np.linalg.norm(normal, axis=1)
        normal /= np.maximum(norm[:, None], 1e-30)
        # Keep opposite windings separate: a two-sided sheet can be intentional.
        distance = np.einsum('ij,ij->i', normal, g[:, 0])
        return normal, distance, norm / 2
    sn, sd, sa = planes(source)
    cn, cd, ca = planes(candidate)
    keys = np.column_stack([np.rint(sn / .0001), np.rint(sd / .02)]).astype(np.int64)
    groups = defaultdict(list)
    for i, key in enumerate(keys):
        if sa[i] > 1e-12:
            groups[tuple(key)].append(i)
    removed = np.zeros(len(candidate), bool)
    patches = []
    records = []
    for members in groups.values():
        broad_panel = sa[members].sum() >= 10000
        if (len(members) < minimum_source_triangles and not broad_panel) or sa[members].sum() < minimum_area_mm2:
            continue
        g = source[members]
        normal = sn[members[np.argmax(sa[members])]]
        origin = g[0, 0]
        plane_error = float(np.max(abs((g - origin) @ normal)))
        if plane_error > plane_tolerance_mm:
            continue
        x = np.cross(np.eye(3)[np.argmin(abs(normal))], normal)
        x /= np.linalg.norm(x)
        y = np.cross(normal, x)
        basis = np.array([x, y])
        projected = (g - origin) @ basis.T
        domain = sh.union_all(sh.polygons(projected), grid_size=.001)
        if domain.is_empty or not domain.is_valid or domain.geom_type not in ('Polygon', 'MultiPolygon'):
            continue
        # Simplify only redundant/near-collinear boundary vertices. Preserve all
        # components and holes, including openings much smaller than 17 mm.
        panel = sh.simplify(domain, boundary_tolerance_mm, preserve_topology=True)
        topology = lambda p: (len(sh.get_parts(p)), sum(len(q.interiors) for q in sh.get_parts(p)))
        if topology(panel) != topology(domain) or not panel.is_valid:
            continue
        edge_error = float(sh.hausdorff_distance(domain.boundary, panel.boundary, densify=.25))
        symmetric_area = float(sh.area(sh.symmetric_difference(domain, panel)))
        if edge_error > boundary_tolerance_mm + .002 or symmetric_area > domain.length * (boundary_tolerance_mm + .002):
            continue
        # All nearly coplanar overlapping candidate faces must be replaceable;
        # otherwise retain this entire group rather than leave overlapping faces.
        ids = np.flatnonzero((~removed) & (cn @ normal > 1 - 1e-7) &
                             (abs((candidate - origin) @ normal).max(1) <= plane_tolerance_mm))
        # A collapse can tilt panel triangles into neighboring shallow bevels.
        # Include those faces only inside the same finite source panel and the
        # accepted 1 mm neighborhood. Distinct parallel layers remain separate.
        near = np.flatnonzero((~removed) & (cn @ normal > math.cos(math.radians(5))) &
                              (abs((candidate - origin) @ normal).max(1) <= 1.05) &
                              (np.ptp((candidate - origin) @ normal, axis=1) > plane_tolerance_mm))
        ids = np.union1d(ids, near)
        cp = sh.polygons((candidate[ids] - origin) @ basis.T)
        touching = sh.area(sh.intersection(cp, domain)) > 1e-8
        ids, cp = ids[touching], cp[touching]
        if not len(ids) and not broad_panel:
            continue
        if not np.all(sh.covered_by(cp, sh.buffer(domain, 1.05))):
            continue
        faces = sh.get_parts(sh.constrained_delaunay_triangles(panel))
        if not len(faces):
            continue
        combined = sh.union_all(faces)
        area_error = float(sh.area(sh.symmetric_difference(combined, panel)))
        if area_error > max(1e-6, panel.area * 1e-10):
            continue
        uv = np.array([np.asarray(f.exterior.coords)[:3] for f in faces])
        new = origin + uv @ basis
        flip = np.cross(new[:, 1] - new[:, 0], new[:, 2] - new[:, 0]) @ normal < 0
        new[flip] = new[flip][:, ::-1]
        # A patch may add faces to repair a damaged 1 mm panel. Only accept it
        # if it is no more expensive than its original source tessellation.
        if len(new) > len(members):
            continue
        removed[ids] = True
        patches.append(new)
        records.append({'source_triangles': len(members), 'candidate_triangles': len(ids),
                        'panel_triangles': len(new), 'source_area_mm2': float(domain.area),
                        'components': topology(domain)[0], 'holes': topology(domain)[1],
                        'maximum_source_plane_distance_mm': plane_error,
                        'projected_boundary_distance_mm': edge_error,
                        'projected_symmetric_difference_mm2': symmetric_area,
                        'triangulation_symmetric_difference_mm2': area_error})
    return np.flatnonzero(~removed), (np.concatenate(patches) if patches else np.empty((0, 3, 3))), records
