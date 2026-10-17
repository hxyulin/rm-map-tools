# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explicit native-profile collision meshes for sockets and folded panels.

Callers select rigid source domains and error policies. Native wires preserve
large openings; profile approximation and small-hole closure are deliberate.
This module does not bind scoring detectors or install runtime geometry.
"""
import math
import numpy as np


def simplify_loop(points, tolerance_mm):
    """Simplify a closed sampled loop with a finite chord-distance allowance.

    Two anchored Douglas-Peucker chains retain topology ordering. A caller must
    still validate the resulting polygon/solid: this is not a simplicity proof.
    """
    p = np.asarray(points, float)
    if p.ndim != 2 or len(p) < 3 or not np.isfinite(p).all() or not math.isfinite(tolerance_mm) or tolerance_mm <= 0: raise ValueError('invalid profile loop')
    def chain(q):
        if len(q) < 3: return q
        v = q[-1] - q[0]; den = v @ v
        t = np.clip((q - q[0]) @ v / max(den, 1e-30), 0, 1)
        d = np.linalg.norm(q - q[0] - t[:, None] * v, axis=1); k = int(d.argmax())
        if d[k] <= tolerance_mm: return q[[0, -1]]
        return np.concatenate([chain(q[:k + 1])[:-1], chain(q[k:])])
    k = int(np.linalg.norm(p - p[0], axis=1).argmax())
    result = np.concatenate([chain(p[:k + 1])[:-1], chain(np.concatenate([p[k:], p[:1]]))[:-1]])
    if len(result) < 3: raise ValueError('profile loop collapsed')
    return result


def native_loops(face, *, chord_error_mm=.2, boundary_error_mm=.5, close_holes_below_mm=0):
    """Sample native planar wires, optionally omit strictly small inner holes.

    The opening-width measurement includes complete native curves. Outer loops
    are never removed. The source face and its neighbors remain unchanged.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.TopAbs import TopAbs_WIRE, TopAbs_REVERSED
    from OCP.TopoDS import TopoDS
    from cad_wall_fill import shape_map
    from cad_surface_lods import wire_width_bound_mm
    if not all(math.isfinite(v) and v > 0 for v in [chord_error_mm, boundary_error_mm]) or not math.isfinite(close_holes_below_mm) or close_holes_below_mm < 0: raise ValueError('invalid native profile policy')
    face = TopoDS.Face(face); surface = BRepAdaptor_Surface(face)
    if surface.GetType() != GeomAbs_Plane: raise ValueError('profile face is not planar')
    outer = BRepTools.OuterWire_s(face); wires = shape_map(face, TopAbs_WIRE); loops = []; records = []
    for i in range(1, wires.Extent() + 1):
        wire = TopoDS.Wire(wires.FindKey(i)); is_outer = wire.IsSame(outer)
        width = None if is_outer else wire_width_bound_mm(face, wire)
        if width is not None and width < close_holes_below_mm:
            records.append({'wire_index': i, 'operation': 'close-small-hole', 'native_width_bound_mm': width}); continue
        explorer = BRepTools_WireExplorer(wire, face); parts = []
        while explorer.More():
            edge = explorer.Current(); curve = BRepAdaptor_Curve(edge)
            sampling = GCPnts_QuasiUniformDeflection(curve, chord_error_mm)
            if not sampling.IsDone() or sampling.NbPoints() < 2: raise ValueError('native curve sampling failed')
            q = np.array([sampling.Value(j).Coord() for j in range(1, sampling.NbPoints() + 1)])
            if edge.Orientation() == TopAbs_REVERSED: q = q[::-1]
            parts.append(q); explorer.Next()
        if not parts or any(np.linalg.norm(a[-1] - b[0]) > .01 for a, b in zip(parts, parts[1:] + parts[:1])): raise ValueError('native profile wire has a gap')
        p = np.concatenate([q[:-1] for q in parts]); simplified = simplify_loop(p, boundary_error_mm)
        loops.append({'outer': is_outer, 'points_mm': simplified})
        records.append({'wire_index': i, 'operation': 'retain-profile', 'outer': is_outer, 'native_width_bound_mm': width, 'sampled_vertices': len(p), 'vertices': len(simplified)})
    return loops, {'chord_error_mm': chord_error_mm, 'sampled_boundary_allowance_mm': boundary_error_mm, 'strict_hole_closure_width_mm': close_holes_below_mm, 'wires': records}


def mesh_metrics(p, t):
    """Check shared-edge closed topology, winding and signed volume of a mesh."""
    p = np.asarray(p, float); t = np.asarray(t)
    edges = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]); keys, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    directions = np.where(edges[:, 0] < edges[:, 1], 1, -1)
    g = p[t] - p.mean(0); volume = float(np.einsum('ij,ij->i', g[:, 0], np.cross(g[:, 1], g[:, 2])).sum() / 6)
    return {'closed_oriented_manifold': bool(len(t) and np.all(counts == 2) and np.all(np.bincount(inverse, weights=directions) == 0)),
            'boundary_edges': int((counts == 1).sum()), 'nonmanifold_edges': int((counts > 2).sum()), 'signed_volume_mm3': volume}


def prism_mesh(loops, normal, depth_mm):
    """Extrude a finite polygon with holes into a closed triangle prism.

    Front loops use millimetre XYZ coordinates. The extrusion goes opposite the
    outward front normal, preserving through-openings and one shared edge mesh.
    """
    import vtk
    n = np.asarray(normal, float)
    if n.shape != (3,) or not np.isfinite(n).all() or np.linalg.norm(n) < 1e-12 or not math.isfinite(depth_mm) or depth_mm <= 0 or not loops or sum(r['outer'] for r in loops) != 1: raise ValueError('invalid panel prism')
    n /= np.linalg.norm(n); x = np.cross(np.eye(3)[np.argmin(abs(n))], n); x /= np.linalg.norm(x); y = np.cross(n, x)
    origin = np.asarray(loops[0]['points_mm'])[0]; front = []; boundaries = []
    for row in loops:
        p = np.asarray(row['points_mm'], float)
        if p.ndim != 2 or p.shape[1] != 3 or len(p) < 3 or not np.isfinite(p).all() or abs((p - origin) @ n).max() > .01: raise ValueError('nonplanar prism profile')
        local = np.column_stack(((p - origin) @ x, (p - origin) @ y)); signed = np.sum(local[:, 0] * np.roll(local[:, 1], -1) - local[:, 1] * np.roll(local[:, 0], -1)) / 2
        if (signed > 0) != row['outer']: p = p[::-1]
        boundaries.append(np.arange(sum(len(q) for q in front), sum(len(q) for q in front) + len(p))); front.append(p)
    p = np.concatenate(front); local = np.column_stack(((p - origin) @ x, (p - origin) @ y)); pts = vtk.vtkPoints(); pts.SetDataTypeToDouble()
    for a, b in local: pts.InsertNextPoint(float(a), float(b), 0)
    cells = vtk.vtkCellArray()
    for ids in boundaries:
        cells.InsertNextCell(len(ids) + 1)
        for k in [*ids, ids[0]]: cells.InsertCellPoint(int(k))
    data = vtk.vtkPolyData(); data.SetPoints(pts); data.SetLines(cells); op = vtk.vtkContourTriangulator(); op.SetInputData(data); op.Update(); output = op.GetOutput()
    if op.GetTriangulationError() or not output.GetNumberOfCells(): raise ValueError('panel polygon triangulation failed')
    caps = []
    for i in range(output.GetNumberOfCells()):
        cell = output.GetCell(i)
        if cell.GetNumberOfPoints() != 3: raise ValueError('panel cap is not triangular')
        caps.append([cell.GetPointId(k) for k in range(3)])
    caps = np.array(caps); xyz = p[caps]; flip = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0]) @ n < 0; caps[flip] = caps[flip][:, [0, 2, 1]]
    size = len(p); q = np.concatenate([p, p - n * depth_mm]); sides = []
    for loop in boundaries:
        for a, b in zip(loop, np.roll(loop, -1)): sides.extend([[a, b + size, b], [a, a + size, b + size]])
    t = np.concatenate([caps, caps[:, ::-1] + size, np.array(sides)])
    proof = mesh_metrics(q, t)
    if not proof['closed_oriented_manifold'] or proof['signed_volume_mm3'] <= 0: raise ValueError('panel prism is not closed and outward oriented')
    # Triangulator area must agree with the signed loop area including holes.
    expected = sum(np.sum(local[ids, 0] * np.roll(local[ids, 1], -1) - local[ids, 1] * np.roll(local[ids, 0], -1)) / 2 for ids in boundaries)
    if abs(proof['signed_volume_mm3'] / depth_mm - expected) > max(.001, expected * 1e-7): raise ValueError('panel cap fills an opening or overlaps')
    return q, t, proof


def revolve_profile(loops_ry_mm, *, angular_segments, axis=1, center_mm=(0, 0, 0)):
    """Revolve complete meridian loops, including recesses, into a closed mesh.

    Meridian coordinates are radius and axial height in millimetres. Loops are
    oriented outer/inner boundaries of one or more source section faces. Axis
    vertices are shared; no generic cap is placed across a socket or undercut.
    """
    if type(angular_segments) is not int or angular_segments < 8 or axis not in (0, 1, 2): raise ValueError('invalid revolution policy')
    center = np.asarray(center_mm, float)
    if center.shape != (3,) or not np.isfinite(center).all(): raise ValueError('invalid revolution frame')
    radial_axes = [a for a in range(3) if a != axis]; angles = np.arange(angular_segments) * 2 * np.pi / angular_segments; positions = []; triangles = []
    for row in loops_ry_mm:
        loop = np.asarray(row['points_ry_mm'], float)
        if loop.ndim != 2 or loop.shape[1] != 2 or len(loop) < 3 or not np.isfinite(loop).all() or np.any(loop[:, 0] < -1e-6): raise ValueError('invalid meridian loop')
        loop = loop.copy(); loop[abs(loop[:, 0]) < 1e-6, 0] = 0
        signed = np.sum(loop[:, 0] * np.roll(loop[:, 1], -1) - loop[:, 1] * np.roll(loop[:, 0], -1)) / 2
        if (signed > 0) != row['outer']: loop = loop[::-1]
        offset = len(positions)
        for r, h in loop:
            for a in angles:
                p = center.copy(); p[axis] += h; p[radial_axes] += [r * math.cos(a), r * math.sin(a)]; positions.append(p)
        for j in range(len(loop)):
            k = (j + 1) % len(loop)
            for a in range(angular_segments):
                b = (a + 1) % angular_segments; u, v, w, z = offset + j * angular_segments + a, offset + j * angular_segments + b, offset + k * angular_segments + b, offset + k * angular_segments + a
                triangles.extend([[u, v, w], [u, w, z]])
    p, inverse = np.unique(np.array(positions), axis=0, return_inverse=True); t = inverse[np.array(triangles)]
    xyz = p[t]; t = t[np.linalg.norm(np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0]), axis=1) > 1e-12]
    if axis == 1: t = t[:, ::-1]
    proof = mesh_metrics(p, t)
    if not proof['closed_oriented_manifold'] or proof['signed_volume_mm3'] <= 0: raise ValueError('revolved profile is not a closed outward mesh')
    return p, t, proof


def meridian_section(solid, *, angle_rad, axis=1, radius_limit_mm, height_range_mm, center_mm=(0, 0, 0), chord_error_mm=.1, boundary_error_mm=.5):
    """Intersect an immutable native solid with a finite radial half-plane.

    Returned meridian loops include every section face and its holes. The caller
    must compare the revolution with other azimuths; one meridian is an explicit
    symmetry approximation, not a proof that the original object is rotational.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.gp import gp_Pnt
    from cad_wall_fill import shape_map
    if not math.isfinite(angle_rad) or not math.isfinite(radius_limit_mm) or radius_limit_mm <= 0 or axis not in (0, 1, 2) or len(height_range_mm) != 2 or not all(math.isfinite(v) for v in height_range_mm) or height_range_mm[1] <= height_range_mm[0] or not BRepCheck_Analyzer(solid).IsValid(): raise ValueError('invalid native section domain')
    center = np.asarray(center_mm, float)
    if center.shape != (3,) or not np.isfinite(center).all(): raise ValueError('invalid native section center')
    radial_axes = [a for a in range(3) if a != axis]; radial = np.zeros(3); radial[radial_axes] = [math.cos(angle_rad), math.sin(angle_rad)]
    polygon = BRepBuilderAPI_MakePolygon()
    for r, h in [(0, height_range_mm[0]), (radius_limit_mm, height_range_mm[0]), (radius_limit_mm, height_range_mm[1]), (0, height_range_mm[1])]:
        p = center + r * radial; p[axis] += h; polygon.Add(gp_Pnt(*map(float, p)))
    polygon.Close(); plane = BRepBuilderAPI_MakeFace(polygon.Wire()).Face(); op = BRepAlgoAPI_Common(solid, plane); op.SetNonDestructive(True); op.Build()
    if not op.IsDone() or not BRepCheck_Analyzer(op.Shape()).IsValid(): raise ValueError('native section failed')
    faces = shape_map(op.Shape(), TopAbs_FACE); loops = []; records = []
    if not faces.Extent(): raise ValueError('native section is empty')
    for i in range(1, faces.Extent() + 1):
        profiles, proof = native_loops(faces.FindKey(i), chord_error_mm=chord_error_mm, boundary_error_mm=boundary_error_mm)
        for row in profiles:
            p = row['points_mm'] - center; loops.append({'outer': row['outer'], 'points_ry_mm': np.column_stack((p @ radial, p[:, axis]))})
        records.append(proof)
    return loops, {'angle_rad': angle_rad, 'axis': axis, 'center_mm': center.tolist(), 'section_faces': faces.Extent(), 'profiles': records,
                   'scope': 'Native solid/finite-half-plane intersection, sampled and simplified meridian wires. Revolution is a caller-qualified symmetry approximation.'}
