#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Bind reviewed Low geometry to native 2027 structure rules without remeshing."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from cad_document import CadDocument
from export_repaired_game import ROOT, SOURCE_SHA, dump, descendants
from gltf_scene import read_glb, write_glb, scene_nodes, mesh_instances, local_matrix
from plan_cad_lods import digest
from export_elements import quaternion_xyzw

SCREENS = [4099408, 4121375, 4143351]
SHIELDS = [4314593, 4353403, 4392221]
OUTPOST_SCREENS = [2200540, 2302471, 2404428]


def fit_detector(points, triangles, optical):
    """Fit the existing source-envelope detector policy, not the Low surface."""
    g = points[triangles[optical]]
    cross = np.cross(g[:, 1] - g[:, 0], g[:, 2] - g[:, 0]); weight = np.linalg.norm(cross, axis=1)
    normal = cross / np.maximum(weight[:, None], 1e-30)
    radial = g.mean(1); radial[:, 1] = 0
    normal[(normal * radial).sum(1) < 0] *= -1
    groups = {}
    for i, n in enumerate(normal):
        if weight[i] > 1e-10: groups.setdefault(tuple(np.round(n, 2)), []).append(i)
    if not groups: raise ValueError('missing optical source plane')
    chosen = max(groups.values(), key=lambda ids: weight[ids].sum())
    n = np.average(normal[chosen], axis=0, weights=weight[chosen]); n /= np.linalg.norm(n)
    width = np.cross([0., 1., 0.], n); width /= np.linalg.norm(width)
    basis = np.stack([n, width, np.cross(n, width)], axis=1)
    projected = points[triangles].reshape(-1, 3) @ basis
    lo, hi = projected.min(0), projected.max(0); middle = (lo + hi) / 2
    middle[0] = hi[0] + .0015
    half = (hi - lo)[1:] / 2
    if np.any(half < .01) or np.any(half > .071): raise ValueError(f'implausible detector envelope {half}')
    return basis @ middle, basis, half


def fit_base():
    path = ROOT / 'out/rmuc2027-base-textures-final/base-visual.glb'
    d, b = read_glb(path); results = []
    for body in SCREENS:
        points = []; faces = []; optical = []; offset = 0
        for ni, pi, p, t, mi in mesh_instances(d, b):
            if d['nodes'][ni].get('extras', {}).get('source_unit_id') != body: continue
            color = d['materials'][mi].get('extras', {}).get('step_colour_srgb')
            points.append(p); faces.append(t + offset); offset += len(p)
            optical.extend([color == [1., 0., 0.]] * len(t))
        results.append(fit_detector(np.concatenate(points), np.concatenate(faces), np.array(optical)))
    return results, {str(path.relative_to(ROOT)): digest(path)}


def outpost_sources():
    hierarchy_path = ROOT / 'out/rmuc2027-hierarchy/hierarchy.json'
    h = json.loads(hierarchy_path.read_text()); results = []; mappings = {}; inputs = {}
    for index, screen in enumerate(OUTPOST_SCREENS):
        cid = f'outpost/rotor/module-{index}'
        component = next(c for c in h['components'] if c['id'] == cid)
        folder = ROOT / 'out/rmuc2027-equipment-pipeline' / cid
        native = json.loads((folder / 'native.json').read_text())
        if digest(folder / 'native.npz') != native['native_npz_sha256'] or digest(folder / 'source.step') != native['source_step_sha256']: raise ValueError('native detector input changed')
        data = np.load(folder / 'native.npz'); p, t, u = [data[k] for k in ['positions_mm', 'triangles', 'unit_ids']]
        boxes = {int(unit): np.array([p[t[u == unit]].min((0, 1)), p[t[u == unit]].max((0, 1))]) for unit in np.unique(u)}
        unit_map = {}; claimed = set()
        with CadDocument.from_step(folder / 'source.step', workers=1, intern_layers=True) as cad:
            for body in component['solid_body_ids']:
                lo, hi, _ = cad.model.body_bbox(cad.index.r(component['export_body_ids'][str(body)]))
                distances = sorted((float(abs(box - [lo, hi]).max()), unit) for unit, box in boxes.items() if unit not in claimed)
                if distances[0][0] > 1 or (len(distances) > 1 and distances[1][0] - distances[0][0] < .05): raise ValueError('ambiguous native solid correspondence')
                unit = distances[0][1]; claimed.add(unit); unit_map[unit] = ('body', body)
        remaining = set(boxes) - claimed
        shells = [s for ids in component['shell_ids_by_body'].values() for s in ids]
        if len(remaining) != 1 or len(shells) != 1: raise ValueError('incomplete module shell correspondence')
        unit_map[remaining.pop()] = ('shell', shells[0]); mappings[cid] = unit_map
        selected_unit = next(unit for unit, (kind, sid) in unit_map.items() if sid == screen)
        selected = u == selected_unit; faces = t[selected]
        palette = data['palette'].tolist(); colors = [palette[i] for i in data['material_ids'][selected]]
        optical = np.array([str(c).startswith('0.0000,1.0000,1.0000') for c in colors])
        results.append(fit_detector(p / 1000, faces, optical))
        for name in ['source.step', 'native.npz', 'native.json']: inputs[str((folder / name).relative_to(ROOT))] = digest(folder / name)
    return results, mappings, inputs


def reparent_joint(doc, node_indices, identity, pivot, axis, limits):
    """Insert a pivot/joint pair while preserving every rest-pose world matrix."""
    worlds = {i: w for i, w, _ in scene_nodes(doc)}; parents = {i: p for i, w, p in scene_nodes(doc)}
    parent = parents[node_indices[0]]
    if any(parents[i] != parent for i in node_indices): raise ValueError('joint members do not share a parent')
    frame = np.eye(4); frame[:3, 3] = pivot
    origin = len(doc['nodes']); joint = origin + 1
    local_origin = np.linalg.inv(worlds[parent]) @ frame
    for i in node_indices:
        doc['nodes'][i]['matrix'] = (np.linalg.inv(frame) @ worlds[i]).ravel(order='F').tolist()
        for key in ['translation', 'rotation', 'scale']: doc['nodes'][i].pop(key, None)
    children = doc['nodes'][parent]['children']; first = min(children.index(i) for i in node_indices)
    children[:] = [i for i in children if i not in node_indices]; children.insert(first, origin)
    doc['nodes'].extend([{'name': identity + '.origin', 'matrix': local_origin.ravel(order='F').tolist(), 'children': [joint]},
                         {'name': identity, 'extras': {'rm': {'id': identity, 'axis': list(axis), 'limits_m': limits}}, 'children': list(node_indices)}])
    updated = {i: w for i, w, _ in scene_nodes(doc)}
    if any(not np.allclose(w, updated[i], atol=1e-10, rtol=0) for i, w in worlds.items()): raise ValueError('joint insertion moved geometry')


def bind(package, out):
    if out.exists(): raise ValueError('output exists')
    manifest = json.loads((package / 'manifest.json').read_text())
    if manifest['source_sha256'] != SOURCE_SHA: raise ValueError('wrong source')
    bases, inputs = fit_base(); towers, mappings, other = outpost_sources(); inputs.update(other)
    rows = []; rhs = []
    for center, basis, half in towers:
        n = basis[[0, 2], 0]; tangent = np.array([-n[1], n[0]])
        rows.append(tangent); rhs.append(tangent @ center[[0, 2]])
    xz = np.linalg.lstsq(rows, rhs, rcond=None)[0]; pivot = np.array([xz[0], 1.14, xz[1]])
    motions = {}; parts = []; audit = json.loads((ROOT / 'out/rmuc2027-base-analysis/audit.json').read_text())
    source_boxes = {u['source_id']: np.array(u['bbox_mm']) / 1000 for u in audit['units']}
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as temp:
        stage = Path(temp) / 'field'; shutil.copytree(package, stage)
        for asset, relative in [('base', 'equipment/base.glb'), ('outpost', 'outpost.glb')]:
            files = [('visual', relative), ('collision', relative.replace('.glb', '-collision.glb'))]
            records = {}; visual_motions = None
            for kind, filename in files:
                path = stage / filename; doc, blob = read_glb(path); local_parts = {}; motion_groups = []
                original_payload = {k: copy.deepcopy(doc.get(k)) for k in ['meshes', 'materials', 'accessors', 'bufferViews', 'images', 'textures', 'samplers']}
                inherited = {}
                for i, w, parent in scene_nodes(doc):
                    node = doc['nodes'][i]; e = node.get('extras', {}); cid = e.get('component_id') or e.get('composition_occurrence', {}).get('component_id') or inherited.get(parent)
                    inherited[i] = cid
                    if 'mesh' not in node: continue
                    unit = e.get('source_unit_id', e.get('source_native_shell_index', e.get('native_shell_index')))
                    source_kind = 'unit'; source_id = unit
                    if asset == 'base' and unit is not None: name = f'source_body_{unit}'; source_kind = 'body-or-shell'
                    elif cid in mappings and unit in mappings[cid]:
                        source_kind, source_id = mappings[cid][unit]; name = f'source_{source_kind}_{source_id}'
                    else: name = f'part/{cid or asset}/unit/{unit if unit is not None else i}'
                    if name in local_parts: raise ValueError('duplicate runtime part identity')
                    node['name'] = name; local_parts[name] = i
                    node.setdefault('extras', {}).setdefault('rm', {}).update(part_id=name, component_id=cid, source_id=source_id, source_kind=source_kind)
                    record = records.setdefault(name, {'id': asset + '/' + name, 'asset': asset, 'source_id': source_id, 'source_kind': source_kind, 'component_id': cid})
                    record[kind + '_node'] = name
                if asset == 'base':
                    for index, body in enumerate(SHIELDS):
                        name = f'source_body_{body}'
                        if name not in local_parts: raise ValueError('missing shield partition')
                        box = source_boxes[body]; axis = box.mean(0); axis[1] = 0; axis /= np.linalg.norm(axis)
                        identity = f'base.armor.{index}'; nodes = [local_parts[name]]
                        reparent_joint(doc, nodes, identity, np.zeros(3), axis, [0., .25])
                        records[name]['motion_id'] = identity
                        motion_groups.append({'id': identity, 'bodies': [name], 'axis': axis.tolist(), 'pivot_m': [0., 0., 0.], 'limits': [0., .25]})
                else:
                    rotor = [i for i, n in enumerate(doc['nodes']) if n.get('name') == 'rotor']
                    if len(rotor) != 1: raise ValueError('missing source rotor assembly')
                    moving = [name for name, ni in local_parts.items() if ni in descendants(doc, rotor[0])]
                    if len(moving) != 18: raise ValueError('incomplete rotor module membership')
                    reparent_joint(doc, rotor, 'outpost.spin', pivot, [0., 1., 0.], None)
                    for name in moving: records[name]['motion_id'] = 'outpost.spin'
                    motion_groups.append({'id': 'outpost.spin', 'bodies': sorted(moving), 'axis': [0., 1., 0.], 'pivot_m': pivot.tolist(), 'limits': None})
                if kind == 'visual': visual_motions = motion_groups
                elif motion_groups != visual_motions: raise ValueError('drawing/physics motion partitions differ')
                if any(doc.get(k) != value for k, value in original_payload.items()): raise ValueError('binding altered geometry or appearance payload')
                write_glb(path, doc, blob)
                _, actual_blob = read_glb(path)
                if actual_blob[:len(blob)] != blob: raise ValueError('binding changed binary payload')
            motions[asset] = visual_motions; parts.extend(records.values())
            mfile = stage / ('equipment/manifest.json' if asset == 'base' else 'manifest.json')
            m = json.loads(mfile.read_text()); entry = m['assets'][asset]
            entry.update(visual_sha256=digest(stage / relative), collision_sha256=digest(stage / relative.replace('.glb', '-collision.glb')))
            dump(mfile, m)
        world = {'bases': [None, None], 'outposts': [None, None], 'zones': [], 'rotor_direction': 1}
        for asset, fitted in [('base', bases), ('outpost', towers)]:
            m = json.loads((stage / ('equipment/manifest.json' if asset == 'base' else 'manifest.json')).read_text())
            for placement in m['assets'][asset]['placements_in_source_arena_frame']:
                r = local_matrix({'rotation': placement['rotation_xyzw']})[:3, :3]
                t = np.array(placement['translation_m']) - [0, 1.6243436, manifest['floor_top_source_z_m']]
                side = 0 if t[0] >= 0 else 1; detectors = []
                for center, basis, half in fitted:
                    x, y, z, w = quaternion_xyzw(r @ basis)
                    detectors.append({'pose': {'translation_m': (r @ center + t).tolist(), 'rotation_wxyz': [w, x, y, z]}, 'half_m': half.tolist()})
                if asset == 'base': world['bases'][side] = detectors
                else: world['outposts'][side] = {'pivot_m': (r @ pivot + t).tolist(), 'axis': (r @ [0., 1., 0.]).tolist(), 'detectors': detectors}
        bindings = {'schema_version': 2, 'ruleset': 'rmuc2027-v1.0.0', 'source_sha256': SOURCE_SHA, 'world': world,
                    'base_motion': motions['base'], 'outpost_motion': motions['outpost'], 'parts': parts,
                    'report': {'base': {'detector_bodies': SCREENS}, 'outpost': {'detector_bodies': OUTPOST_SCREENS}},
                    'limitations': ['Source-envelope rectangular detectors, not final dot-matrix masks.', 'Illustrative 0.25m base shield travel retained.', 'Rotor modules include their attached source surface-model LED shells; shared tower stays fixed.', 'Rune/Dart/Tech Core remain source-rest-pose scenery; their unsupported gameplay is not enabled.']}
        dump(stage / 'rmuc2027-bindings.json', bindings)
        m = json.loads((stage / 'manifest.json').read_text()); m['rmuc2027_bindings'] = {'file': 'rmuc2027-bindings.json', 'sha256': digest(stage / 'rmuc2027-bindings.json')}; dump(stage / 'manifest.json', m)
        dump(stage / 'structure-binding-build.json', {'script_sha256': digest(Path(__file__)), 'inputs_sha256': inputs,
            'package_manifest_sha256': digest(package / 'manifest.json'), 'base_audit_sha256': digest(ROOT / 'out/rmuc2027-base-analysis/audit.json'),
            'rest_world_matrices_preserved': True, 'mesh_attributes_and_indices_unchanged': True, 'part_count': len(parts)})
        stage.rename(out)
    print(json.dumps({'output': str(out), 'parts': len(parts), 'outpost_moving_parts': len(motions['outpost'][0]['bodies'])}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--package', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); bind(a.package.resolve(), a.out.resolve())
