#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Rank STEP detail costs and benchmark tessellation from a JSON audit job.

Usage: ocpenv/bin/python python/audit_geometry.py rules/audit-resource.example.json
No source geometry or installed assets are changed. Face/body indices are local
OCCT import indices, qualified by the STEP checksum, not semantic or STEP IDs.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import time

from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL, TopAbs_WIRE, TopAbs_EDGE, TopAbs_REVERSED
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label, IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

from export_policy import validate_block
from mesh_parts import tessellate
from validate_parts import read_part


def shape_map(shape, kind):
    result = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, kind, result)
    return result


def compound(doc):
    roots = Sequence_TDF_Label()
    XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots)
    result = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(result)
    for i in range(1, roots.Length() + 1):
        builder.Add(result, XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)))
    return result


def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        return None
    return [[p.X(), p.Y(), p.Z()] for p in (box.CornerMin(), box.CornerMax())]


def describe_face(face):
    surface = BRepAdaptor_Surface(face)
    kind = str(surface.GetType()).rsplit('_', 1)[-1]
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    result = {'surface': kind, 'area_mm2': abs(props.Mass())}
    wires = shape_map(face, TopAbs_WIRE)
    result['inner_wires'] = max(0, wires.Extent() - 1)
    if kind == 'Plane' and result['inner_wires']:
        outer = BRepTools.OuterWire_s(face)
        result['circular_inner_radii_mm'] = []
        for i in range(1, wires.Extent() + 1):
            wire = wires.FindKey(i)
            if wire.IsSame(outer):
                continue
            edges = shape_map(wire, TopAbs_EDGE)
            circles = []
            for j in range(1, edges.Extent() + 1):
                curve = BRepAdaptor_Curve(TopoDS.Edge(edges.FindKey(j)))
                if str(curve.GetType()).rsplit('_', 1)[-1] != 'Circle':
                    break
                circles.append(curve.Circle())
            if not circles or len(circles) != edges.Extent():
                continue
            circle = circles[0]
            if any(abs(c.Radius() - circle.Radius()) > 1e-6 or
                   c.Location().Distance(circle.Location()) > 1e-6 or
                   abs(c.Axis().Direction().Dot(circle.Axis().Direction())) < 1 - 1e-8 for c in circles):
                continue
            length = GProp_GProps()
            BRepGProp.LinearProperties_s(wire, length)
            if abs(length.Mass() - 2 * math.pi * circle.Radius()) <= max(1e-6, length.Mass() * 1e-6):
                result['circular_inner_radii_mm'].append(circle.Radius())
    if kind in ('Cylinder', 'Sphere', 'Torus'):
        analytic = getattr(surface, kind)()
        result['radius_mm'] = analytic.MinorRadius() if kind == 'Torus' else analytic.Radius()
    if kind == 'Cylinder':
        result['inward_cylinder_candidate'] = face.Orientation() == TopAbs_REVERSED
    if kind == 'Sphere':
        radius = result['radius_mm']
        fraction = result['area_mm2'] / (4 * math.pi * radius * radius)
        result['sphere_area_fraction'] = fraction
        u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
        rectangular_area = radius * radius * (u1 - u0) * (math.sin(v1) - math.sin(v0))
        # Full longitude plus exact rectangular area rejects clipped/holed patches.
        complete = abs(u1 - u0 - 2 * math.pi) < 1e-6 and abs(rectangular_area - result['area_mm2']) < max(1e-6, result['area_mm2'] * 1e-6)
        result['sphere_patch'] = ('full' if complete and abs(fraction - 1) < 1e-6 else
                                  'hemisphere' if complete and abs(fraction - 0.5) < 1e-6 and
                                  (abs(v0) < 1e-6 or abs(v1) < 1e-6) else 'trimmed')
    return result


def inspect_topology(doc):
    shape = compound(doc)
    faces = shape_map(shape, TopAbs_FACE)
    solids = shape_map(shape, TopAbs_SOLID)
    records = {i: describe_face(TopoDS.Face(faces.FindKey(i))) for i in range(1, faces.Extent() + 1)}
    bodies = []
    solid_shells = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    for i in range(1, solids.Extent() + 1):
        TopExp.MapShapes_s(solids.FindKey(i), TopAbs_SHELL, solid_shells)
    shells = shape_map(shape, TopAbs_SHELL)
    candidates = [('solid', i, solids.FindKey(i)) for i in range(1, solids.Extent() + 1)]
    candidates += [('shell', i, shells.FindKey(i)) for i in range(1, shells.Extent() + 1)
                   if not solid_shells.Contains(shells.FindKey(i))]
    for kind, i, body in candidates:
        owned = shape_map(body, TopAbs_FACE)
        ids = [faces.FindIndex(owned.FindKey(j)) for j in range(1, owned.Extent() + 1)]
        box = bounds(body)
        spans = [b - a for a, b in zip(*box)] if box else []
        bodies.append({'body_kind': kind, 'body_index': i, 'face_indices': ids, 'bbox_mm': box,
                       'max_extent_mm': max(spans, default=0),
                       'surfaces': dict(Counter(records[j]['surface'] for j in ids))})
    return records, bodies


def summarize(records, bodies, triangle_counts, small_body_mm, small_hole_radius_mm):
    groups = defaultdict(lambda: {'faces': 0, 'triangles': 0})
    small_curves = defaultdict(lambda: {'faces': 0, 'triangles': 0})
    holes = []
    perforated = []
    for i, face in records.items():
        n = triangle_counts[i]
        group = groups[face['surface']]
        group['faces'] += 1
        group['triangles'] += n
        if face.get('radius_mm', math.inf) <= small_hole_radius_mm:
            group = small_curves[face['surface']]
            group['faces'] += 1
            group['triangles'] += n
        if face.get('inward_cylinder_candidate') and face['radius_mm'] <= small_hole_radius_mm:
            holes.append({'face_index': i, 'triangles': n, **face})
        if face['surface'] == 'Plane' and face['inner_wires']:
            perforated.append({'face_index': i, 'triangles': n, **face})
    ranked = [{**body, 'triangles': sum(triangle_counts[i] for i in body['face_indices'])} for body in bodies]
    small = [body for body in ranked if body['max_extent_mm'] <= small_body_mm]
    # Count shared faces only once. Candidate groups overlap; never sum their savings.
    small_faces = {i for body in small for i in body['face_indices']}
    return {'triangles': sum(triangle_counts.values()), 'surfaces': dict(groups),
            'topology': {'solids': sum(b['body_kind'] == 'solid' for b in bodies),
                         'shells_outside_solids': sum(b['body_kind'] == 'shell' for b in bodies),
                         'single_face_shells': sum(b['body_kind'] == 'shell' and len(b['face_indices']) == 1 for b in bodies)},
            'small_radius_surfaces': dict(small_curves),
            'small_bodies': {'count': len(small), 'triangles': sum(triangle_counts[i] for i in small_faces),
                             'largest': sorted(small, key=lambda b: -b['triangles'])[:30]},
            'hole_candidates': {'faces': len(holes), 'wall_triangles': sum(f['triangles'] for f in holes),
                                'largest': sorted(holes, key=lambda f: -f['triangles'])[:30]},
            'perforated_planes': {'faces': len(perforated), 'triangles': sum(f['triangles'] for f in perforated),
                                  'small_circular_openings': sum(sum(r <= small_hole_radius_mm for r in f.get('circular_inner_radii_mm', [])) for f in perforated),
                                  'largest': sorted(perforated, key=lambda f: -f['triangles'])[:30]},
            'largest_bodies': sorted(ranked, key=lambda b: -b['triangles'])[:30]}


def read_config(path):
    config = json.loads(path.read_text())
    allowed = {'schema_version', 'package', 'parts', 'output', 'samples', 'small_body_mm', 'small_hole_radius_mm'}
    if not isinstance(config, dict) or set(config) - allowed or type(config.get('schema_version')) is not int or config['schema_version'] != 1:
        raise ValueError('expected audit schema_version 1 with known fields')
    for key in ('package', 'output'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError(f'{key}: expected path')
        config[key] = (path.parent / config[key]).resolve()
    if not isinstance(config.get('parts'), list) or not config['parts'] or any(not isinstance(p, str) or not p for p in config['parts']):
        raise ValueError('parts: expected nonempty list of exact product names')
    if len(set(config['parts'])) != len(config['parts']):
        raise ValueError('parts: duplicate name')
    samples = config.get('samples')
    if not isinstance(samples, dict) or not samples:
        raise ValueError('samples: expected named tolerance pairs')
    for name, sample in samples.items():
        if not name:
            raise ValueError('sample names must be nonempty')
        validate_block({'visual': sample}, f'samples.{name}')
        if set(sample) != {'linear_deflection_mm', 'angular_deflection_rad'}:
            raise ValueError(f'samples.{name}: both tolerances required')
    for key, default in [('small_body_mm', 30), ('small_hole_radius_mm', 5)]:
        value = config.setdefault(key, default)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key}: expected finite positive millimetres')
    return config


def run(config):
    manifest = json.loads((config['package'] / 'parts.json').read_text())
    selected = []
    for name in config['parts']:
        matches = [p for p in manifest['parts'] if p['name'] == name]
        if len(matches) != 1:
            raise ValueError(f'{name}: expected one matching part, found {len(matches)}')
        selected.append(matches[0])
    result = {'schema_version': 1, 'units': 'millimetres',
              'scope': 'Unique imported part geometry, not placed scene counts. Candidate groups overlap. Small shells may be individual faces of larger objects, not removable hardware. Inward cylinder orientation alone does not prove a hole in an open shell. No automatic removals.',
              'index_contract': 'OCCT import indices qualified by source_sha256; not STEP entity IDs or semantic IDs.',
              'thresholds': {k: config[k] for k in ('small_body_mm', 'small_hole_radius_mm')}, 'parts': []}
    for part in selected:
        path = (config['package'] / part['file']).resolve()
        if not path.is_relative_to(config['package']):
            raise ValueError('part path escapes package')
        start = time.perf_counter()
        doc, reader, error = read_part(str(path))
        if error:
            raise ValueError(f'{path}: {error}')
        faces, bodies = inspect_topology(doc)
        record = {'name': part['name'], 'product_id': part['product_id'], 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'read_and_topology_seconds': time.perf_counter() - start,
                  'faces': faces, 'samples': {}}
        print(f"{part['name']}: {len(faces)} faces, {len(bodies)} bodies", flush=True)
        for name, params in config['samples'].items():
            counts = {}
            stats = {}
            start = time.perf_counter()
            mesh = tessellate(doc, params['linear_deflection_mm'], params['angular_deflection_rad'], stats,
                              face_observer=lambda i, face, n: counts.__setitem__(i, n))
            if mesh is None or stats.get('unmeshed_faces'):
                raise ValueError(f'{part["name"]}/{name}: incomplete tessellation: {stats}')
            report = summarize(faces, bodies, counts, config['small_body_mm'], config['small_hole_radius_mm'])
            assert report['triangles'] == len(mesh[1])
            report.update(tolerance=params, seconds=time.perf_counter() - start, recovery=stats,
                          mesh_bbox_mm=[mesh[0].min(axis=0).tolist(), mesh[0].max(axis=0).tolist()],
                          face_triangles=counts)
            record['samples'][name] = report
            print(f"  {name}: {report['triangles']:,} triangles, {report['seconds']:.2f}s", flush=True)
            del mesh
        result['parts'].append(record)
        del doc, reader
    config['output'].parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects prior baselines.
    with config['output'].open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    args = parser.parse_args()
    try:
        config = read_config(args.config.resolve())
        if config['output'].exists():
            raise ValueError(f'output already exists: {config["output"]}')
        run(config)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
