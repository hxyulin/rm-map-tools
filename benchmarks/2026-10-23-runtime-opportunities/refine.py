# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reconstruct source planar domains across same-owner/material mesh seams."""
import argparse
from collections import Counter, defaultdict
import copy
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_planar_panels import rebuild_panels
from gltf_scene import accessor, read_glb, scene_nodes, write_glb
from simplify_package import append_accessor, compact, protected, scene_triangles


def digest(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def structural(mat, primitive):
    if set(primitive['attributes']) - {'POSITION', 'NORMAL'}:
        return False
    if protected(primitive.get('extras', {}).get('rm', {})):
        return False
    if any('Texture' in k for k in mat.get('pbrMetallicRoughness', {})) or any('Texture' in k for k in mat):
        return False
    if max(mat.get('emissiveFactor', [0, 0, 0])) > 0:
        return False
    rgb = mat.get('extras', {}).get('step_colour_srgb')
    return rgb is None or np.ptp(rgb) < .15


def refine_asset(source, candidate, target):
    sd, sb = read_glb(source)
    cd, cb = read_glb(candidate)
    if len(sd['nodes']) != len(cd['nodes']) or sd['materials'] != cd['materials']:
        raise ValueError('candidate hierarchy/materials differ from source')
    source_worlds = {i: w for i, w, _ in scene_nodes(sd)}
    worlds = {i: w for i, w, _ in scene_nodes(cd)}
    mesh_uses = Counter(sd['nodes'][i]['mesh'] for i in source_worlds if 'mesh' in sd['nodes'][i])
    if any(not np.array_equal(w, worlds[i]) for i, w in source_worlds.items()):
        raise ValueError('candidate node poses differ')
    scopes = {}
    inherited_protection = {}
    groups = defaultdict(list)
    drop = defaultdict(set)
    for i, world, parent in scene_nodes(sd):
        node = sd['nodes'][i]
        e = node.get('extras', {})
        rm = e.get('rm', {})
        own_scope = e.get('component_id') or rm.get('part_id') or rm.get('id')
        scopes[i] = i if own_scope else scopes.get(parent, i)
        inherited_protection[i] = protected(rm) or inherited_protection.get(parent, False)
        if 'mesh' not in node or inherited_protection[i]:
            continue
        # Keep already shared definitions in their own local frames; baking
        # repeated instances into component batches expands stored geometry.
        scope = i if mesh_uses[node['mesh']] > 1 else scopes[i]
        if not np.allclose(np.linalg.svd(worlds[scope][:3, :3], compute_uv=False), 1, atol=1e-8):
            continue
        sp = sd['meshes'][node['mesh']]['primitives']
        cp = cd['meshes'][cd['nodes'][i]['mesh']]['primitives']
        if len(sp) != len(cp):
            raise ValueError('primitive correspondence changed')
        matrix = np.eye(4) if scope == i else np.linalg.inv(worlds[scope]) @ world
        for pi, (s, c) in enumerate(zip(sp, cp)):
            material = sd['materials'][s['material']]
            if not structural(material, s) or not structural(material, c):
                continue
            appearance = json.dumps({k: v for k, v in material.items() if k not in ('name', 'extras')}, sort_keys=True)
            def load(doc, blob, primitive):
                p = accessor(doc, blob, primitive['attributes']['POSITION']).astype(float)
                t = (accessor(doc, blob, primitive['indices']) if 'indices' in primitive else np.arange(len(p))).reshape(-1, 3)
                if np.linalg.det(matrix[:3, :3]) < 0:
                    t = t[:, ::-1]
                g = (p @ matrix[:3, :3].T + matrix[:3, 3])[t] * 1000
                if 'NORMAL' in primitive['attributes']:
                    normal = accessor(doc, blob, primitive['attributes']['NORMAL']).astype(float)[t] @ np.linalg.inv(matrix[:3, :3])
                    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-30)
                else:
                    n = np.cross(g[:, 1] - g[:, 0], g[:, 2] - g[:, 0])
                    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
                    normal = np.repeat(n[:, None], 3, axis=1)
                return g, normal
            source_g, _ = load(sd, sb, s)
            candidate_g, candidate_n = load(cd, cb, c)
            groups[scope, appearance].append((i, pi, s['material'], source_g, candidate_g, candidate_n))
    changed = copy.deepcopy(cd)
    binary = bytearray(cb)
    rows = []
    generated = []
    mesh_cache = {}
    for (scope, appearance), pieces in groups.items():
        source_g = np.concatenate([r[3] for r in pieces])
        candidate_g = np.concatenate([r[4] for r in pieces])
        candidate_n = np.concatenate([r[5] for r in pieces])
        keep, patch, panels = rebuild_panels(source_g, candidate_g)
        # Even without a panel replacement, compatible source meshes can share
        # one primitive inside this scope without moving any baseline surfaces.
        if not panels and len(pieces) < 2:
            continue
        patch_n = np.cross(patch[:, 1] - patch[:, 0], patch[:, 2] - patch[:, 0])
        patch_n /= np.maximum(np.linalg.norm(patch_n, axis=1, keepdims=True), 1e-30)
        patch_n = np.round(patch_n, 7)
        patch_n /= np.maximum(np.linalg.norm(patch_n, axis=1, keepdims=True), 1e-30)
        g = np.concatenate([candidate_g[keep], patch])
        n = np.concatenate([candidate_n[keep], np.repeat(patch_n[:, None], 3, axis=1)])
        if not len(g):
            raise ValueError('refinement removed entire group')
        positions = np.ascontiguousarray(g.reshape(-1, 3) / 1000, dtype='<f4')
        normals = np.ascontiguousarray(n.reshape(-1, 3), dtype='<f4')
        # Weld complete attributes, preserving hard normal seams. Identical
        # derived definitions can still share one mesh across separate owners.
        attributes, inverse = np.unique(np.column_stack([positions, normals]), axis=0, return_inverse=True)
        positions = np.ascontiguousarray(attributes[:, :3])
        normals = np.ascontiguousarray(attributes[:, 3:])
        indices = np.ascontiguousarray(inverse, dtype=np.uint32)
        key = (appearance, positions.tobytes(), normals.tobytes(), indices.tobytes())
        mesh = mesh_cache.get(key)
        if mesh is None:
            primitive = {'attributes': {'POSITION': append_accessor(changed, binary, positions, 'VEC3', 5126),
                                        'NORMAL': append_accessor(changed, binary, normals, 'VEC3', 5126)},
                         'indices': append_accessor(changed, binary, indices, 'SCALAR', 5125),
                         'material': pieces[0][2],
                         'extras': {'derived_geometry': True, 'native_identity_claim': False,
                                    'planar_panel_refinement': True, 'inspection_only': True}}
            mesh = len(changed['meshes'])
            changed['meshes'].append({'primitives': [primitive]})
            mesh_cache[key] = mesh
        child = len(changed['nodes'])
        changed['nodes'].append({'name': 'derived-planar-panels-' + str(scope) + '-' + str(mesh), 'mesh': mesh,
                                 'extras': {'derived_geometry': True, 'native_identity_claim': False, 'inspection_only': True}})
        changed['nodes'][scope].setdefault('children', []).append(child)
        generated.append((child, positions, normals, indices))
        for i, pi, *_ in pieces:
            drop[i].add(pi)
        rows.append({'scope_node': scope, 'scope_name': cd['nodes'][scope].get('name'),
                     'material': pieces[0][2], 'source_nodes': sorted({r[0] for r in pieces}),
                     'source_primitives': len(pieces), 'source_triangles': len(source_g),
                     'before_triangles': len(candidate_g), 'after_triangles': len(g),
                     'panels': panels})
    for i, dropped in drop.items():
        old_mesh = cd['meshes'][cd['nodes'][i]['mesh']]
        remaining = [p for j, p in enumerate(old_mesh['primitives']) if j not in dropped]
        if remaining:
            changed['nodes'][i]['mesh'] = len(changed['meshes'])
            changed['meshes'].append({**copy.deepcopy(old_mesh), 'primitives': copy.deepcopy(remaining)})
        else:
            changed['nodes'][i].pop('mesh')
    changed['asset'].setdefault('extras', {}).update(inspection_only=True, collision_approved=False,
                                                    refinement='source-planar-domains-v1')
    payload = compact(changed, binary)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_glb(target, changed, payload)
    actual, blob = read_glb(target)
    for child, p, n, indices in generated:
        prim = actual['meshes'][actual['nodes'][child]['mesh']]['primitives'][0]
        if not np.array_equal(accessor(actual, blob, prim['attributes']['POSITION']), p) or not np.array_equal(accessor(actual, blob, prim['attributes']['NORMAL']), n):
            raise ValueError('written panel attributes differ')
        if not np.array_equal(accessor(actual, blob, prim['indices']), indices):
            raise ValueError('written panel indices differ')
    actual_worlds = {i: w for i, w, _ in scene_nodes(actual)}
    if any(not np.array_equal(w, actual_worlds[i]) for i, w in worlds.items()):
        raise ValueError('refinement moved original node')
    # Protected primitives stay byte-identical; only mesh slots of selected
    # structural primitives are replaced. Materials/images are preserved.
    if actual['materials'] != cd['materials']:
        raise ValueError('material table changed')
    return {'source_sha256': digest(source), 'candidate_sha256': digest(candidate),
            'sha256': digest(target), 'before': scene_triangles(cd), 'after': scene_triangles(actual),
            'groups': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT.parent / 'rm-simulator/field-2027')
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-runtime-opportunities')
    args = parser.parse_args()
    out = args.out.resolve()
    audit = json.loads((out / 'audit.json').read_text())
    results = {}
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = args.package / relative
        for name, asset in json.loads(manifest.read_text())['assets'].items():
            for role in ('visual', 'collision'):
                source = manifest.parent / asset[role]
                if digest(source) != audit['assets'][name + '/' + role]['sha256']:
                    raise ValueError('source changed from audit')
                candidate = out / 'meshes' / (role + '-1mm') / asset[role]
                target = out / 'refined' / (role + '-1mm') / asset[role]
                row = refine_asset(source, candidate, target)
                row['placements'] = max(1, len(asset['placements_in_source_arena_frame']))
                row['output'] = str(target.relative_to(out))
                results[name + '/' + role] = row
                print(name, role, row['before'] * row['placements'], '->', row['after'] * row['placements'],
                      'panels', sum(len(r['panels']) for r in row['groups']), flush=True)
    report = {'assets': results, 'producer_sha256': {str(p.relative_to(ROOT)): digest(p) for p in
              (Path(__file__), ROOT / 'python/cad_planar_panels.py')},
              'scope': 'Inspection-only source planar reconstruction; protected materials and independently owned component/part/joint scopes remain separate. Curved remainder stays at accepted 1 mm. Not approved collision or complete surface coverage.'}
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = args.package / relative
        for name, asset in json.loads(manifest.read_text())['assets'].items():
            for role in ('visual', 'collision'):
                if digest(manifest.parent / asset[role]) != audit['assets'][name + '/' + role]['sha256']:
                    raise ValueError('runtime input mutated')
    (out / 'refined.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
