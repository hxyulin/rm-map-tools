#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check exported collider payloads, Energy socket rays and major Dart openings."""
import argparse
import json
import math
from pathlib import Path
from audit import ROOT, native
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
from cad_collision_profiles import native_loops, mesh_metrics
from gltf_scene import read_glb, mesh_instances
from mesh_quality import distances
from plan_cad_lods import digest
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCP.gp import gp_Lin, gp_Pnt, gp_Dir
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopoDS import TopoDS


def polydata(p, t):
    poly = vtk.vtkPolyData(); points = vtk.vtkPoints(); points.SetData(numpy_to_vtk(np.ascontiguousarray(p), deep=True)); poly.SetPoints(points)
    cells = vtk.vtkCellArray(); cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(t), 3), t]).astype(np.int64).ravel(), deep=True)); poly.SetPolys(cells); return poly


def raycaster(p, t):
    locator = vtk.vtkStaticCellLocator(); locator.SetDataSet(polydata(p, t)); locator.BuildLocator()
    def ray(start, end):
        u = vtk.reference(0.); hit = [0., 0., 0.]; pc = [0., 0., 0.]; sub = vtk.reference(0); cell = vtk.reference(0)
        return np.array(hit) if locator.IntersectWithLine(start, end, 1e-8, u, hit, pc, sub, cell) else None
    return ray


def source_raycaster(shell):
    native_ray = IntCurvesFace_ShapeIntersector(); native_ray.Load(shell, 1e-7)
    def ray(start, end):
        delta = np.asarray(end) - start; length = np.linalg.norm(delta); direction = delta / length
        native_ray.Perform(gp_Lin(gp_Pnt(*map(float, start)), gp_Dir(*map(float, direction))), 0, float(length))
        if not native_ray.NbPnt(): return None
        i = min(range(1, native_ray.NbPnt() + 1), key=native_ray.WParameter)
        return np.array(start) + direction * native_ray.WParameter(i)
    return ray


def exported(path, mesh, *, energy=False):
    doc, blob = read_glb(path); p = mesh['positions_mm']; t = mesh['triangles']; units = mesh['unit_ids']; count = 0
    geometry = []; faces = []; unit_parts = []; cursor = 0
    for index, _, q, f, _ in mesh_instances(doc, blob):
        node = doc['nodes'][index]; owner = node['extras']['source_native_shell_index']; ids = np.ones(len(t), bool) if energy else units == owner
        if not np.array_equal(q[f], (p[t[ids]] / 1000).astype(np.float32).astype(float)): raise ValueError('exported collider geometry/order differs from recorded mesh')
        if not node['extras']['collision_only'] or not node['extras']['derived_geometry']: raise ValueError('missing collision approximation metadata')
        geometry.append(q * 1000); faces.append(f + cursor); unit_parts.extend([owner] * len(f)); cursor += len(q); count += len(f)
    if count != len(t): raise ValueError('exported collider count mismatch')
    return np.concatenate(geometry), np.concatenate(faces), np.array(unit_parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve()
    energy = json.loads((out / 'energy-summary.json').read_bytes()); panels = json.loads((out / 'panels-summary.json').read_bytes()); results = []
    e = next(v for v in energy['variants'] if v['stage'] == 'meridian-1-24'); cid = energy['id']; folder = out / cid; mesh = np.load(folder / (e['stage'] + '.npz'))
    for name, sha in e['outputs_sha256'].items():
        if digest(folder / name) != sha: raise ValueError('Energy payload changed')
    p, t, _ = exported(folder / (e['stage'] + '.glb'), mesh, energy=True)
    # glTF uses separate normal vertices; weld exact exported positions for topology.
    welded, inverse = np.unique(p, axis=0, return_inverse=True); topology = mesh_metrics(welded, inverse[t])
    if not topology['closed_oriented_manifold']: raise ValueError('exported Energy collider is open')
    _, _, _, shells, _ = native(ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step'); source_ray = source_raycaster(shells.FindKey(1)); collision_ray = raycaster(p, t)
    socket = []
    for radius in [0, 5, 10]:
        for angle in np.arange(16) * 2 * math.pi / 16:
            start = np.array([radius * math.cos(angle), -1., radius * math.sin(angle)]); end = start + [0, 152, 0]; a, b = source_ray(start, end), collision_ray(start, end)
            # The native stop has small azimuth-dependent screw/retainer relief.
            # Keep the deep socket, allowing at most 2 mm local stop relief fill.
            if a is None or b is None or np.linalg.norm(a - b) > 2: raise ValueError('Energy socket stop changed beyond the local relief allowance')
            socket.append(float(np.linalg.norm(a - b)))
    samples = []
    for y in np.linspace(10, 90, 17):
        for radius in [0, 8, 10]:
            for angle in np.arange(16) * 2 * math.pi / 16: samples.append([radius * math.cos(angle), y, radius * math.sin(angle)])
    clearance = float(distances(np.array(samples), p, t).min())
    if clearance < 8.5: raise ValueError('sampled 17 mm projectile socket clearance failed')
    probes = np.array([[0., 50, 0], [28, 12, 0], [0, 130, 0], [25, 50, 0]])
    points = vtk.vtkPoints(); points.SetData(numpy_to_vtk(probes, deep=True)); data = vtk.vtkPolyData(); data.SetPoints(points); inside = vtk.vtkSelectEnclosedPoints(); inside.SetInputData(data); inside.SetSurfaceData(polydata(p, t)); inside.Update(); occupancy = [bool(inside.IsInside(i)) for i in range(len(probes))]
    if occupancy != [False, False, True, True]: raise ValueError('Energy socket/recess occupancy changed: ' + str(occupancy))
    results.append({'id': cid, 'triangles': len(t), 'exported_closed_topology': topology, 'socket_stop_rays': len(socket), 'local_socket_stop_relief_allowance_mm': 2, 'maximum_socket_stop_shift_mm': max(socket), 'sampled_projectile_centers': len(samples), 'minimum_sampled_socket_surface_clearance_mm': clearance, 'socket_recess_occupancy': occupancy})
    for row in panels['components']:
        cid = row['id']; folder = out / cid; mesh = np.load(folder / 'panels.npz')
        for name, sha in row['outputs_sha256'].items():
            if digest(folder / name) != sha: raise ValueError('Dart payload changed')
        p, t, units = exported(folder / 'panels.glb', mesh); _, _, source_faces, shells, _ = native(ROOT / 'out/rmuc2027-equipment-pipeline' / cid / 'source.step'); checks = 0; skipped = 0; worst_vertices = 0
        composition = json.loads((ROOT / 'out/rmuc2027-residual-equipment/composition.json').read_bytes()); original = next(r for r in composition['components'] if r['id'] == cid); reference = np.load((ROOT / original['candidate_glb']).with_suffix('.npz'))
        for member in np.unique(units):
            old = reference['triangles'][reference['unit_ids'] == member]; current = t[units == member]
            worst_vertices = max(worst_vertices, float(distances(reference['positions_mm'][np.unique(old)], p, current).max()), float(distances(p[np.unique(current)], reference['positions_mm'], old).max()))
        if worst_vertices > 6.005: raise ValueError('exported Dart per-member vertex guard failed ' + cid + ' ' + str(worst_vertices))
        for member in row['members']:
            if not member['accepted']: continue
            owner = member['source_member']; source_ray = source_raycaster(shells.FindKey(owner)); collision_ray = raycaster(p, t[units == owner])
            for panel in member['panels']:
                face = source_faces.FindKey(panel['front_native_face']); normal = np.array(BRepAdaptor_Surface(TopoDS.Face(face)).Plane().Axis().Direction().Coord())
                loops, _ = native_loops(face, close_holes_below_mm=17)
                for loop in loops:
                    if loop['outer']: continue
                    center = loop['points_mm'].mean(0); start = center + normal * 12; end = center - normal * (panel['depth_mm'] + 12)
                    if source_ray(start, end) is not None: skipped += 1; continue
                    # A clear zero-radius CAD ray can graze another plate or a
                    # retainer already closed in the approved visual baseline.
                    # Only test paths that also admit a 17 mm projectile in
                    # that baseline; a centroid alone is not a clearance proof.
                    reference_faces = reference['triangles'][reference['unit_ids'] == owner]
                    if distances(np.linspace(start, end, 17), reference['positions_mm'], reference_faces).min() < 8.5:
                        skipped += 1; continue
                    if collision_ray(start, end) is not None: raise ValueError('Dart major opening center was filled: ' + str((cid, owner, panel['front_native_face'], center.tolist(), collision_ray(start, end).tolist())))
                    checks += 1
        results.append({'id': cid, 'triangles': len(t), 'major_opening_clear_rays': checks, 'skipped_occluded_or_concave_hole_centers': skipped, 'maximum_exported_per_member_vertex_distance_mm': worst_vertices})
    report = {'components': results, 'energy_summary_sha256': digest(out / 'energy-summary.json'), 'panels_summary_sha256': digest(out / 'panels-summary.json'), 'producer_sha256': digest(__file__),
              'scope': 'Actual GLB payloads and owner mapping, closed Energy topology, 48 source-CAD socket stop rays, finite 17 mm sphere-center clearances, socket/recess occupancy, source-clear major Dart opening-center rays and per-member vertex errors. Finite diagnostics, not all trajectories or motion poses.'}
    (out / 'validation.json').write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps(results, indent=2))


if __name__ == '__main__': main()
