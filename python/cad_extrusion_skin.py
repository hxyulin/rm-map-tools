# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Structured, shared-edge LOD for explicitly selected native extrusion faces.

This is a geometric approximation, not a solid edit. Source edges define the
profile; neighboring planar caps use exactly the same sampled boundary. No
material, assembly occurrence or motion owner is merged by this operation.
"""
import math
import numpy as np


def extrusion_skin(faces, selected_face_indices, *, sections,
                   maximum_profile_error_mm=1, sample_count=32769):
    """Return replacement meshes for extrusion strips and their planar caps.

    ``faces`` is a native indexed face map; indices are one-based. Only extrusion
    strips with two translated spline chains and two straight ends are admitted. Their
    monotone profile coordinate is sampled uniformly. All adjacent faces must
    be planar or selected strips; holes in planar caps remain boundary loops.
    Curved edges outside the selected strips cause rejection, never a guessed
    replacement. Errors are dense finite-sample checks, not certified bounds.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_WIRE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.GeomAbs import GeomAbs_Line, GeomAbs_BSplineCurve, GeomAbs_SurfaceOfExtrusion, GeomAbs_Plane
    import vtk

    if type(sections) is not int or sections < 2 or type(sample_count) is not int or sample_count < 1025 or not math.isfinite(maximum_profile_error_mm) or maximum_profile_error_mm <= 0:
        raise ValueError('invalid extrusion LOD policy')
    selected = sorted(set(selected_face_indices))
    if not selected or any(type(i) is not int or i < 1 or i > faces.Extent() for i in selected):
        raise ValueError('invalid source face selection')
    edge_map = []
    def edge_id(edge):
        for i, existing in enumerate(edge_map):
            if existing.IsSame(edge): return i
        edge_map.append(edge); return len(edge_map) - 1

    wires = {}; edges_by_face = {}
    for i in range(1, faces.Extent() + 1):
        face = TopoDS.Face(faces.FindKey(i)); loops = []
        explorer = TopExp_Explorer(face, TopAbs_WIRE)
        while explorer.More():
            wire = BRepTools_WireExplorer(TopoDS.Wire(explorer.Current()), face); loop = []
            while wire.More():
                edge = wire.Current(); loop.append((edge_id(edge), edge.Orientation() == TopAbs_REVERSED)); wire.Next()
            loops.append(loop); explorer.Next()
        wires[i] = loops; edges_by_face[i] = {eid for loop in loops for eid, _ in loop}

    profiles = {}; strips = {}; records = []
    for i in selected:
        face = TopoDS.Face(faces.FindKey(i)); surface = BRepAdaptor_Surface(face)
        if surface.GetType() != GeomAbs_SurfaceOfExtrusion or len(wires[i]) != 1:
            raise ValueError('selected face is not a single-wire extrusion strip')
        curve_edges = [eid for eid, _ in wires[i][0]
                       if BRepAdaptor_Curve(TopoDS.Edge(edge_map[eid])).GetType() == GeomAbs_BSplineCurve]
        straight = [eid for eid, _ in wires[i][0]
                    if BRepAdaptor_Curve(TopoDS.Edge(edge_map[eid])).GetType() == GeomAbs_Line]
        if len(straight) != 2 or len(curve_edges) + 2 != len(wires[i][0]):
            raise ValueError('extrusion boundary is not spline profiles and two lines')
        direction = np.array(surface.Direction().Coord())
        ends = []
        for eid in curve_edges:
            curve = BRepAdaptor_Curve(TopoDS.Edge(edge_map[eid]))
            ends.extend([curve.Value(curve.FirstParameter()).Coord(), curve.Value(curve.LastParameter()).Coord()])
        ends = np.array(ends); projected = ends - (ends @ direction)[:, None] * direction
        _, _, basis = np.linalg.svd(projected - projected.mean(0), full_matrices=False)
        total_span = np.ptp(projected @ basis[0])
        for eid in curve_edges:
            if eid not in profiles:
                curve = BRepAdaptor_Curve(TopoDS.Edge(edge_map[eid])); lo, hi = curve.FirstParameter(), curve.LastParameter()
                params = np.linspace(lo, hi, sample_count)
                dense = np.array([curve.Value(float(u)).Coord() for u in params])
                axis = dense[-1] - dense[0]; axis -= direction * (axis @ direction)
                if np.linalg.norm(axis) < 1e-6: raise ValueError('closed or degenerate extrusion profile')
                axis /= np.linalg.norm(axis); coordinate = (dense - dense[0]) @ axis
                if np.any(np.diff(coordinate) <= 0): raise ValueError('profile is not monotone across the extrusion')
                edge_sections = max(1, round(sections * coordinate[-1] / total_span))
                targets = np.linspace(0, coordinate[-1], edge_sections + 1)
                us = np.interp(targets, coordinate, params)
                points = np.array([curve.Value(float(u)).Coord() for u in us])
                ids = np.clip(np.searchsorted(targets, coordinate) - 1, 0, edge_sections - 1)
                a, b = points[ids], points[ids + 1]; delta = b - a
                frac = np.clip(np.sum((dense - a) * delta, axis=1) / np.sum(delta * delta, axis=1), 0, 1)
                error = float(np.linalg.norm(dense - a - frac[:, None] * delta, axis=1).max())
                if error > maximum_profile_error_mm: raise ValueError('profile exceeds sampled deviation allowance')
                profiles[eid] = points
                records.append({'source_edge_index': eid + 1, 'samples': sample_count, 'sections': edge_sections, 'maximum_sampled_profile_error_mm': error})
        loop = wires[i][0]; start = next(j for j, (eid, _) in enumerate(loop) if eid in straight)
        ordered = loop[start + 1:] + loop[:start + 1]; pair = []; chain = []
        for eid, reverse in ordered:
            if eid in straight:
                if not chain: raise ValueError('extrusion has an empty spline chain')
                if any(np.linalg.norm(a[-1] - b[0]) > .01 for a, b in zip(chain, chain[1:])):
                    raise ValueError('spline chain has a gap')
                pair.append(np.concatenate([q[:-1] for q in chain[:-1]] + [chain[-1]])); chain = []
            else: chain.append(profiles[eid][::-1] if reverse else profiles[eid])
        if len(pair) != 2 or len(pair[0]) != len(pair[1]): raise ValueError('opposing spline chains have incompatible partitions')
        a, b = pair
        if np.linalg.norm(a[0] - b[-1]) < np.linalg.norm(a[0] - b[0]): b = b[::-1]
        shift = b - a; lateral = shift - (shift @ direction)[:, None] * direction
        if np.linalg.norm(lateral, axis=1).max() > .01 or np.ptp(shift @ direction) > .01:
            raise ValueError('boundaries do not form a translated extrusion strip')
        # Both line edges must connect corresponding profile endpoints.
        for eid in straight:
            curve = BRepAdaptor_Curve(TopoDS.Edge(edge_map[eid]))
            ends = np.array([curve.Value(curve.FirstParameter()).Coord(), curve.Value(curve.LastParameter()).Coord()])
            if min(max(np.linalg.norm(ends - np.array([a[k], b[k]])[order], axis=1))
                   for k in [0, -1] for order in [[0, 1], [1, 0]]) > .01:
                raise ValueError('extrusion end does not match its profiles')
        p = np.concatenate([a, b]); n = len(a)
        t = np.array([[j, j + 1, n + j + 1] for j in range(n - 1)] +
                     [[j, n + j + 1, n + j] for j in range(n - 1)], dtype=np.int64)
        # Match the native face normal at a nondegenerate middle triangle.
        from OCP.BRepTools import BRepTools
        from OCP.gp import gp_Pnt, gp_Vec
        u0, u1, v0, v1 = BRepTools.UVBounds_s(face); point = gp_Pnt(); du = gp_Vec(); dv = gp_Vec()
        surface.D1((u0 + u1) / 2, (v0 + v1) / 2, point, du, dv)
        normal = np.cross(du.Coord(), dv.Coord()) * (-1 if face.Orientation() == TopAbs_REVERSED else 1)
        xyz = p[t]; cross = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
        if cross.sum(0) @ normal < 0: t = t[:, [0, 2, 1]]
        strips[i] = (p, t)

    changed = dict(strips); cap_records = []
    for i, eids in edges_by_face.items():
        if i in strips or not eids.intersection(profiles): continue
        face = TopoDS.Face(faces.FindKey(i)); surface = BRepAdaptor_Surface(face)
        if surface.GetType() != GeomAbs_Plane: raise ValueError('profile has an unselected nonplanar neighbor')
        loops = []
        for loop in wires[i]:
            parts = []
            for eid, reversed_ in loop:
                if eid in profiles: points = profiles[eid]
                else:
                    curve = BRepAdaptor_Curve(TopoDS.Edge(edge_map[eid]))
                    if curve.GetType() != GeomAbs_Line: raise ValueError('cap has an unsupported unselected curved boundary')
                    points = np.array([curve.Value(curve.FirstParameter()).Coord(), curve.Value(curve.LastParameter()).Coord()])
                if reversed_: points = points[::-1]
                parts.append(points)
            if any(np.linalg.norm(parts[j][-1] - parts[(j + 1) % len(parts)][0]) > .01 for j in range(len(parts))):
                raise ValueError('cap boundary does not close within native tolerance')
            loops.append(np.concatenate([p[:-1] for p in parts]))
        p = np.concatenate(loops); plane = surface.Plane(); origin = np.array(plane.Location().Coord())
        x = np.array(plane.XAxis().Direction().Coord()); y = np.array(plane.YAxis().Direction().Coord())
        local = np.column_stack(((p - origin) @ x, (p - origin) @ y))
        pts = vtk.vtkPoints(); pts.SetDataTypeToDouble()
        for q in local: pts.InsertNextPoint(float(q[0]), float(q[1]), 0)
        cells = vtk.vtkCellArray(); offset = 0
        for loop in loops:
            cells.InsertNextCell(len(loop) + 1)
            for j in list(range(len(loop))) + [0]: cells.InsertCellPoint(offset + j)
            offset += len(loop)
        poly = vtk.vtkPolyData(); poly.SetPoints(pts); poly.SetLines(cells)
        op = vtk.vtkContourTriangulator(); op.SetInputData(poly); op.Update(); result = op.GetOutput()
        if op.GetTriangulationError() or not result.GetNumberOfCells(): raise ValueError('cap triangulation failed')
        t = np.array([[result.GetCell(j).GetPointId(k) for k in range(3)] for j in range(result.GetNumberOfCells())])
        if any(result.GetCell(j).GetNumberOfPoints() != 3 for j in range(result.GetNumberOfCells())): raise ValueError('cap has nontriangular output')
        normal = np.array(plane.Axis().Direction().Coord()) * (-1 if face.Orientation() == TopAbs_REVERSED else 1)
        xyz = p[t]; cross = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0]); flip = cross @ normal < 0; t[flip] = t[flip][:, [0, 2, 1]]
        # Check the complete polygon area, including every hole, in its plane.
        signed = [float(np.sum(q[:, 0] * np.roll(q[:, 1], -1) - q[:, 1] * np.roll(q[:, 0], -1)) / 2)
                  for q in np.split(local, np.cumsum([len(q) for q in loops])[:-1])]
        expected = abs(sum(signed)); actual = float(np.linalg.norm(cross, axis=1).sum() / 2)
        if abs(actual - expected) > max(.01, expected * 1e-7): raise ValueError('cap triangulation changes polygon area or fills holes')
        changed[i] = (p, t); cap_records.append({'native_face_index': i, 'loops': len(loops), 'triangles': len(t), 'polygon_area_mm2': expected})
    return changed, {'pass': 'shared-edge-extrusion-skin-v1', 'selected_native_faces': selected,
                     'sections': sections, 'profile_allowance_mm': maximum_profile_error_mm,
                     'edge_profiles': records, 'neighbor_caps': cap_records,
                     'scope': 'Native source profiles chorded with shared samples on every adjacent cap. Finite sampled error, not a continuous bound; source topology and materials remain separate.'}
