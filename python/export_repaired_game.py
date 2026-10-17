#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Export the approved repaired Low scene to the simulator's rest-pose layout.

Visual hierarchy, instancing and PBR survive. Physics comes from the preceding
independent collision ledger, never the unbounded Low visual experiment.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from cad_glb_composition import RigidComposer
from gltf_scene import accessor, read_glb, write_glb, scene_nodes, local_matrix
from simplify_package import compact, scene_triangles
from plan_cad_lods import digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0'
GROUPS = {'floor': (5423526, 1), 'base': (5591688, 2), 'outpost': (4878266, 2),
          'rune': (5101408, 1), 'tech-core': (5209710, 2)}
CONTRACT = 'reviewed-cad-proxy-v1'


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def descendants(doc, root):
    result = {root}
    for child in doc['nodes'][root].get('children', []): result.update(descendants(doc, child))
    return result


def trim_appearance(doc):
    """Keep only used PBR/texture/image records without altering their values."""
    primitives = [p for m in doc['meshes'] for p in m['primitives']]
    used = sorted({p['material'] for p in primitives}); mapping = {old: new for new, old in enumerate(used)}
    doc['materials'] = [doc['materials'][i] for i in used]
    for p in primitives: p['material'] = mapping[p['material']]
    slots = []
    for m in doc['materials']:
        for container in [m, m.get('pbrMetallicRoughness', {})]:
            slots.extend(v for k, v in container.items() if k.endswith('Texture') and isinstance(v, dict))
    used = sorted({v['index'] for v in slots}); mapping = {old: new for new, old in enumerate(used)}
    doc['textures'] = [doc.get('textures', [])[i] for i in used]
    for slot in slots: slot['index'] = mapping[slot['index']]
    for key, field in [('images', 'source'), ('samplers', 'sampler')]:
        used = sorted({t[field] for t in doc['textures'] if field in t}); mapping = {old: new for new, old in enumerate(used)}
        doc[key] = [doc.get(key, [])[i] for i in used]
        for t in doc['textures']:
            if field in t: t[field] = mapping[t[field]]


def partition(doc, binary, mesh_nodes, root=0):
    """Extract a subtree, retaining ancestor transforms and all source attributes."""
    changed = copy.deepcopy(doc); keep = set()
    def visit(index):
        node = changed['nodes'][index]
        children = [child for child in node.get('children', []) if visit(child)]
        if index not in mesh_nodes: node.pop('mesh', None)
        if 'mesh' not in node and not children: return False
        node['children'] = children; keep.add(index); return True
    if not visit(root): raise ValueError('empty runtime partition')
    indices = sorted(keep); remap = {old: new for new, old in enumerate(indices)}
    changed['nodes'] = [changed['nodes'][i] for i in indices]
    for node in changed['nodes']:
        node['children'] = [remap[i] for i in node.get('children', [])]
        if not node['children']: node.pop('children')
        if 'extras' in node: node['extras']['inspection_only'] = False
    node = changed['nodes'][remap[root]]
    for key in ['matrix', 'rotation', 'translation', 'scale']: node.pop(key, None)
    changed['scenes'] = [{'nodes': [remap[root]]}]; changed['scene'] = 0
    # Drop orphan meshes before pruning their materials; repack after image pruning.
    payload = compact(changed, binary)
    trim_appearance(changed); payload = compact(changed, payload)
    changed['asset'].setdefault('extras', {}).update(inspection_only=False, runtime_scope='rmuc2027-rest-pose')
    return changed, payload


def signature(doc, root):
    """Canonical mesh references and relative poses, independent of occurrence."""
    worlds = {i: w for i, w, _ in scene_nodes(doc)}; inverse = np.linalg.inv(worlds[root])
    return [(doc['nodes'][i]['mesh'], inverse @ worlds[i]) for i in sorted(descendants(doc, root)) if 'mesh' in doc['nodes'][i]]


def collision_scene(visual, ledger):
    composer = RigidComposer(); d = composer.document
    d['nodes'] = copy.deepcopy(visual['nodes']); d['scenes'] = copy.deepcopy(visual['scenes'])
    for n in d['nodes']: n.pop('mesh', None)
    rows = {r['id']: r for r in ledger['components']}; inputs = {}
    for cid, row in rows.items():
        if row['collision_method'] == 'visual-only marking': continue
        dedicated = row['collision_method'] == 'dedicated candidate'
        key = 'collision' if dedicated else 'visual'
        path = (ROOT / row[key + '_glb']).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != row[key + '_sha256']: raise ValueError('collision ledger input mismatch')
        doc, blob = read_glb(path); composer.append_definition(cid, doc, blob)
        inputs[str(path.relative_to(ROOT))] = digest(path)
    for i, node in enumerate(visual['nodes']):
        cid = node.get('extras', {}).get('component_id')
        if cid and cid not in rows: raise ValueError('unaccounted source component')
        if cid in composer.definitions: composer.instantiate(cid, i)
    if scene_triangles(d) != ledger['totals']['collision_budget_placed']: raise ValueError('collision composition count mismatch')
    d['asset'].setdefault('extras', {}).update(collision_contract=CONTRACT)
    return d, bytes(composer.binary), inputs


def export(out):
    out = Path(out).resolve()
    if out.exists(): raise ValueError('output exists; choose a new directory')
    source = ROOT / 'out/rmuc2027-game-coverage/guarded/guarded-field.glb'
    report_path = source.parent / 'guarded.json'; report = json.loads(report_path.read_text())
    if digest(source) != report['sha256']: raise ValueError('approved visual checksum mismatch')
    ledger_path = ROOT / 'out/rmuc2027-equipment-shells/summary.json'
    ledger = json.loads(ledger_path.read_text()); hierarchy = ROOT / 'out/rmuc2027-hierarchy/hierarchy.json'
    if json.loads(hierarchy.read_text())['source_sha256'] != SOURCE_SHA: raise ValueError('wrong CAD source')
    doc, binary = read_glb(source)
    origin = doc['nodes'][0]['extras']['source_origin_m']
    # Remove only the inspection camera's Y-up/rebasing root. Runtime consumes
    # original numeric CAD Z-up coordinates and performs its own FLU conversion.
    doc['nodes'][0]['matrix'] = np.eye(4).ravel(order='F').tolist()
    worlds = {i: w for i, w, _ in scene_nodes(doc)}
    roots = {}
    for name, (product, count) in GROUPS.items():
        selected = [i for i, n in enumerate(doc['nodes']) if n.get('extras', {}).get('source_product_id') == product]
        if len(selected) != count: raise ValueError(f'{name}: source assembly count differs')
        first = signature(doc, selected[0])
        for i in selected[1:]:
            other = signature(doc, i)
            if len(first) != len(other) or any(a != b or not np.allclose(x, y, atol=1e-10, rtol=0) for (a, x), (b, y) in zip(first, other)): raise ValueError(f'{name}: instances differ')
        roots[name] = selected
    assigned = set(); partitions = {}
    for name, selected in roots.items():
        nodes = set().union(*(descendants(doc, i) for i in selected))
        if assigned & nodes: raise ValueError('overlapping runtime groups')
        assigned.update(nodes); partitions[name] = descendants(doc, selected[0])
    partitions['arena-static'] = set(range(len(doc['nodes']))) - assigned
    collision, cb, inputs = collision_scene(doc, ledger)
    from export_elements import quaternion_xyzw
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as directory:
        stage = Path(directory) / 'field'; (stage / 'equipment').mkdir(parents=True)
        assets = {}; coverage = {}; totals = {'visual': 0, 'collision': 0}; bounds = {}
        for name in ['floor', 'arena-static', 'rune', 'outpost', 'base', 'tech-core']:
            prefix = 'equipment/' if name in ['base', 'tech-core'] else ''
            root = 0 if name in ['floor', 'arena-static'] else roots[name][0]
            if name == 'floor': selection = set().union(*(descendants(doc, i) for i in roots[name]))
            else: selection = partitions[name]
            if name in ['floor', 'arena-static']:
                cselection = set().union(*(descendants(collision, i) for i in roots['floor']))
                if name == 'arena-static': cselection = set(range(len(collision['nodes']))) - set().union(*(descendants(collision, i) for ids in roots.values() for i in ids))
            else: cselection = descendants(collision, root)
            entry = {'placements_in_source_arena_frame': []}
            if root:
                for i in roots[name]:
                    matrix = worlds[i]
                    if not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-10) or np.linalg.det(matrix[:3, :3]) < 0: raise ValueError('placement is not a proper rigid transform')
                    entry['placements_in_source_arena_frame'].append({'translation_m': matrix[:3, 3].tolist(), 'rotation_xyzw': quaternion_xyzw(matrix[:3, :3])})
            coverage[name] = {'source_assembly_nodes': roots.get(name, []), 'placements': max(1, len(entry['placements_in_source_arena_frame']))}
            for kind, document, blob, nodes in [('visual', doc, binary, selection), ('collision', collision, cb, cselection)]:
                chosen = {i for i in nodes if 'mesh' in document['nodes'][i]}
                result, payload = partition(document, blob, chosen, root)
                filename = name + ('-collision' if kind == 'collision' else '') + '.glb'
                target = stage / prefix / filename; write_glb(target, result, payload)
                actual, ab = read_glb(target); triangles = scene_triangles(actual)
                entry[kind] = filename; entry[kind + '_sha256'] = digest(target)
                coverage[name][kind + '_triangles_per_copy'] = triangles
                totals[kind] += triangles * coverage[name]['placements']
                # Independent written-payload round trip of all expanded source positions.
                from gltf_scene import mesh_instances
                original = list(mesh_instances(document, blob)); expected = []
                inverse = np.linalg.inv(worlds[root]) if root else np.eye(4)
                for ni, pi, p, t, mi in original:
                    if ni in chosen: expected.append((p @ inverse[:3, :3].T + inverse[:3, 3])[t])
                exported = [p[t] for ni, pi, p, t, mi in mesh_instances(actual, ab)]
                if len(expected) != len(exported) or any(not np.allclose(a, b, atol=1e-10, rtol=0) for a, b in zip(expected, exported)): raise ValueError('exported positions/winding differ')
                if kind == 'visual':
                    points = np.concatenate(expected).reshape(-1, 3); bounds[name] = [points.min(0).tolist(), points.max(0).tolist()]
            entry['collision_method'] = CONTRACT; assets[name] = entry
        if totals != {'visual': report['placed_triangles'], 'collision': ledger['totals']['collision_budget_placed']}: raise ValueError(f'package coverage differs: {totals}')
        common = {'schema_version': 1, 'units': 'metres', 'season': '2027', 'rest_pose_only': True,
                  'source_sha256': SOURCE_SHA, 'source_file': 'RMUC2027_V1.0.0.stp', 'floor_top_source_z_m': origin[2]}
        dump(stage / 'manifest.json', {**common, 'assets': {k: v for k, v in assets.items() if k not in ['base', 'tech-core']}})
        dump(stage / 'equipment/manifest.json', {**common, 'assets': {k: v for k, v in assets.items() if k in ['base', 'tech-core']}})
        shutil.copy2(ROOT / 'NOTICE.md', stage / 'CAD-NOTICE.md')
        dump(stage / 'runtime-build.json', {'schema_version': 1, 'source_sha256': SOURCE_SHA,
            'visual_sha256': digest(source), 'visual_report_sha256': digest(report_path),
            'collision_ledger_sha256': digest(ledger_path), 'collision_inputs_sha256': inputs,
            'hierarchy_sha256': digest(hierarchy), 'producer_sha256': digest(Path(__file__)),
            'helpers_sha256': {f: digest(ROOT / 'python' / f) for f in ['gltf_scene.py', 'cad_glb_composition.py', 'simplify_package.py', 'export_elements.py']},
            'placed_triangles': totals, 'coverage': coverage, 'bounds_local_m': bounds,
            'collision_contract': CONTRACT, 'motion': 'Source rest pose only; no fabricated native combat/joint bindings.',
            'visual_policy': 'Reviewed Low with camera-independent source-piece coverage restoration; separate preceding collision meshes retained. Visual-only marking definitions excluded from collision.'})
        stage.rename(out)
    print(json.dumps({'output': str(out), 'placed_triangles': totals, 'coverage': coverage}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    export(parser.parse_args().out)
