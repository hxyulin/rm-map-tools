# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose whole source products at exact occurrences, without changing geometry.

Recipes select original subtrees or explicit occurrence paths. Products shared
elsewhere are not pulled in accidentally. The synthetic STEP root is only an
export wrapper; it makes no new claim about mechanical attachment or motion.
"""
import json
from pathlib import Path
import re
import shutil

import numpy as np

from cad_components import select_components


def validate_footing(bounds, footing_product_id):
    """Require a paired tower's footprint and bottom to meet its actual footing."""
    footings = [(low, high) for product, low, high in bounds if product == footing_product_id]
    towers = [(low, high) for product, low, high in bounds if product != footing_product_id]
    if len(footings) != 1 or len(towers) != 1:
        raise ValueError('footing alignment requires exactly one tower and one footing')
    flo, fhi = footings[0]; low, high = towers[0]
    overlap = np.maximum(0, np.minimum(high[:2],fhi[:2])-np.maximum(low[:2],flo[:2]))
    area = float(np.prod(high[:2]-low[:2]))
    if area <= 0 or np.prod(overlap)/area < .9 or abs(low[2]-fhi[2]) > .05:
        raise ValueError('tower footprint/bottom does not meet its selected footing')


def native_bounds_m(native):
    """Exact native surface bounds, including assembly placements, in metres."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from validate_parts import TDF_LabelSequence, XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
    roots = TDF_LabelSequence()
    XCAFDoc_DocumentTool.ShapeTool_s(native.Main()).GetFreeShapes(roots)
    bounds = Bnd_Box()
    for i in range(1, roots.Length()+1):
        BRepBndLib.AddOptimal_s(XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)), bounds, False, False)
    return np.array([bounds.CornerMin().Coord(), bounds.CornerMax().Coord()])/1000


def verify_composition(out, source_sha256):
    """Verify file hashes, native face count and the placed STEP/GLB envelope."""
    from export_field_package import sha256
    from export_step_elements import shape_counts
    from gltf_scene import read_glb_nodes
    from validate_parts import read_part
    out = Path(out)
    report = json.loads((out/'composition.json').read_text())
    if report['source_sha256'] != source_sha256:
        raise ValueError('composition belongs to another source')
    for name, expected in report['files_sha256'].items():
        if sha256(out/name) != expected:
            raise ValueError(f'composition checksum mismatch: {name}')
    native, reader, error = read_part(str(out/'source.step'))
    if error or shape_counts(native)[1] != report['native_faces']:
        raise ValueError(error or 'composition native face count changed')
    to_source = np.array([[1.,0,0],[0,0,-1],[0,1,0]])
    points = [vertices@to_source.T for _,vertices,_,_ in read_glb_nodes(out/'visual.glb')]
    bounds = np.array([np.min([p.min(0) for p in points], axis=0),
                       np.max([p.max(0) for p in points], axis=0)])
    error_m = float(np.max(np.abs(native_bounds_m(native)-bounds)))
    if error_m > .005:
        raise ValueError(f'composition STEP/GLB bounds differ by {error_m} m')
    return error_m


def product_occurrences(catalog):
    """Collapse per-body catalog rows to distinct placed whole-product records."""
    components = {c['id']: c for c in catalog['components']}
    result = {}
    for occurrence in catalog['occurrences']:
        product = components[occurrence['component_id']]['product_id']
        key = (occurrence['root_product_id'], tuple(occurrence['occurrence_path']), product)
        item = {**occurrence, 'product_id': product}
        item.pop('component_id')
        if key in result and result[key] != item:
            raise ValueError('inconsistent body placements within a source product')
        result[key] = item
    return list(result.values())


def compile_compositions(catalog, policy):
    """Resolve source-pinned recipes and reject duplicate or missing occurrences."""
    if policy.get('schema_version') != 1 or policy.get('source_sha256') != catalog['source_sha256']:
        raise ValueError('composition schema/source SHA mismatch')
    occurrences = product_occurrences(catalog)
    result, names = [], set()
    for recipe in policy['compositions']:
        name = recipe['name']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name) or name in names or not recipe.get('evidence'):
            raise ValueError('composition needs a unique safe name and evidence')
        names.add(name)
        if ('subtree' in recipe) == ('occurrence_paths' in recipe):
            raise ValueError('choose exactly one composition selector')
        if 'subtree' in recipe:
            selection = select_components(catalog, recipe['subtree'])
            chosen = product_occurrences({**catalog, 'occurrences': selection['occurrences']})
        else:
            paths = recipe['occurrence_paths']
            if len({tuple(p) for p in paths}) != len(paths):
                raise ValueError('duplicate requested occurrence path')
            chosen = [o for o in occurrences if o['occurrence_path'] in paths]
            if len(chosen) != len(paths):
                raise ValueError('requested source occurrence path is absent or ambiguous')
        if not chosen:
            raise ValueError('empty composition')
        result.append({**recipe, 'occurrences': chosen})
    return result


def export_composition(document, recipe, definitions, out, splitter):
    """Write exact-source STEP and instanced GLB, rebased by translation only.

    definitions maps product IDs to native-tessellated product-local GLBs and
    native face counts. Source matrices are in millimetres; GLB vertices are in
    metres. Only the GLB receives the single source Z-up to glTF Y-up conversion.
    """
    from export_field_package import GlbWriter, sha256
    from export_step_elements import write_assembly, shape_counts
    from gltf_scene import read_glb_local_nodes
    from validate_parts import read_part
    import provenance

    if splitter.ix is not document.index or splitter.m is not document.model:
        raise ValueError('splitter belongs to another source document')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    geometries, points, placed_bounds = {}, [], []
    for occurrence in recipe['occurrences']:
        product = occurrence['product_id']
        if product not in geometries:
            geometries[product] = list(read_glb_local_nodes(definitions[product]['glb']))
        matrix = np.array(occurrence['source_world_matrix'], float)
        matrix[:3, 3] /= 1000
        placed = [vertices @ matrix[:3, :3].T + matrix[:3, 3]
                  for _, vertices, _, _, _ in geometries[product]]
        points.extend(placed)
        placed_bounds.append((product, np.min([p.min(0) for p in placed],axis=0),
                              np.max([p.max(0) for p in placed],axis=0)))
    if 'footing_product_id' in recipe:
        validate_footing(placed_bounds, recipe['footing_product_id'])
    low = np.min([p.min(0) for p in points], axis=0)
    high = np.max([p.max(0) for p in points], axis=0)
    origin_m = (low+high)/2
    origin_m[2] = low[2]
    rebase_mm = np.eye(4); rebase_mm[:3, 3] = -origin_m*1000
    to_yup = np.array([[1.,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
    writer = GlbWriter(recipe['name'], provenance.glb_asset('cad_composition.py', document.source_path, document.source_sha256))
    items = []
    for i, occurrence in enumerate(recipe['occurrences']):
        product = occurrence['product_id']
        local_mm = rebase_mm @ np.array(occurrence['source_world_matrix'], float)
        items.append((document.index.r(product), local_mm))
        local_m = local_mm.copy(); local_m[:3, 3] /= 1000
        for name, vertices, triangles, colors, _ in geometries[product]:
            writer.add_node(f'{i}-{name}', vertices, triangles, colors, matrix=to_yup@local_m,
                            extras={'source_product_id': product, 'source_occurrence_path': occurrence['occurrence_path']})
    writer.write(out/'visual.glb')
    shutil.copyfile(Path(__file__).resolve().parents[1]/'NOTICE.md', out/'NOTICE.md')
    write_assembly(splitter, recipe['name'], recipe['name'], items, str(out/'source.step'), document.source_sha256)
    native, reader, error = read_part(str(out/'source.step'))
    if error:
        raise ValueError(error)
    native_counts = shape_counts(native)
    expected_faces = sum(definitions[o['product_id']]['native_faces'] for o in recipe['occurrences'])
    if native_counts[1] != expected_faces:
        raise ValueError(f'composition native face count changed: {native_counts[1]} != {expected_faces}')
    expected_bounds = np.array([low, high])-origin_m
    bounds_error_m = float(np.max(np.abs(native_bounds_m(native)-expected_bounds)))
    if bounds_error_m > .005:
        raise ValueError(f'composition STEP/GLB bounds differ by {bounds_error_m} m')
    document.verify_source()
    report = {**recipe, 'source_sha256': document.source_sha256,
              'source_origin_mm': (origin_m*1000).tolist(),
              'coordinate_contract': 'STEP: source axes, mm, translated origin; GLB: same local frame in m, single Z-up to Y-up rotation',
              'native_faces': native_counts[1], 'native_solids': native_counts[0],
              'step_glb_bounds_error_m': bounds_error_m,
              'placed_triangles': writer.triangles,
              'files_sha256': {f: sha256(out/f) for f in ('source.step', 'visual.glb', 'NOTICE.md')}}
    (out/'composition.json').write_text(json.dumps(report, indent=2)+'\n')
    return report
