#!/usr/bin/env python3
"""Read-only armor inventory. Writes only the dedicated audit output directory.

Run from the repository root with ocpenv/bin/python. Requires the native Base
audit regenerated using the command in README.md. Does not run a reduction pass.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from gltf_scene import read_glb, mesh_instances, scene_nodes
from cad_dense_lod import surface_samples
from mesh_quality import distances

OUT = ROOT / 'out/rmuc2027-armor-fidelity-audit'
PKG = ROOT.parent / 'rm-simulator/field-2027'
SHA = 'a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0'
SCREENS = [4099408, 4121375, 4143351]
BASE_SHELLS = [4723785, 4693907, 4664029]
BASE_SIDE_LIGHTS = [4566871, 4564115, 4561335]
BASE_SMALL_SHELLS = [
    [4694643, 4694827, 4695011, 4695195, 4723877, 4723969, 4724061, 4724153, 4724245, 4724337],
    [4664765, 4664949, 4665133, 4665317, 4693999, 4694091, 4694183, 4694275, 4694367, 4694459],
    [4634887, 4635071, 4635255, 4635439, 4664121, 4664213, 4664305, 4664397, 4664489, 4664581],
]
SHIELDS = [4314593, 4353403, 4392221]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def color(mat):
    rgb = mat.get('extras', {}).get('step_colour_srgb')
    return ','.join(f'{v:.4f}' for v in rgb) if rgb is not None else 'unresolved'


def summary(pieces):
    g = np.concatenate([g for g, _ in pieces])
    materials = defaultdict(int)
    signatures = []
    for triangles, appearance in pieces:
        materials[appearance] += len(triangles)
        # Geometry multiset, independent of mesh/accessor order and triangle winding.
        q = np.round(triangles.reshape(-1, 3), 6).reshape(-1, 3, 3)
        q = np.array([sorted(t.tolist()) for t in q], dtype='<f8')
        signatures.extend(hashlib.sha256(t.tobytes() + appearance.encode()).digest() for t in q)
    return {'triangles': len(g), 'bbox_mm': [g.min((0, 1)).tolist(), g.max((0, 1)).tolist()],
            'triangles_by_appearance': dict(materials),
            'geometry_material_multiset_sha256': hashlib.sha256(b''.join(sorted(signatures))).hexdigest()}


def load_glb(path):
    d, b = read_glb(path)
    components = {}
    identities = {}
    result = defaultdict(list)
    locators = defaultdict(list)
    for i, _, parent in scene_nodes(d):
        e = d['nodes'][i].get('extras', {})
        components[i] = (e.get('component_id') or e.get('composition_occurrence', {}).get('component_id')
                         or components.get(parent))
        identities[i] = e.get('source_unit_id', e.get('rm', {}).get('source_id', e.get('source_native_shell_index')))
        if identities[i] is None and components[i] == components.get(parent):
            identities[i] = identities.get(parent)
    for ni, pi, p, t, mi in mesh_instances(d, b):
        n = d['nodes'][ni]
        e = n.get('extras', {})
        rm = e.get('rm', {})
        sid = identities[ni]
        # Outpost source_id on fixed components is a native ordinal, not a STEP ID.
        if sid is None:
            sid = rm.get('source_id')
        if sid is None:
            sid = e.get('source_native_shell_index')
        key = f'{components[ni]}|{sid}'
        mat = d['materials'][mi]
        appearance = json.dumps(mat, sort_keys=True, separators=(',', ':'))
        result[key].append((p[t] * 1000, appearance))
        locators[key].append({'node': ni, 'name': n['name'], 'primitive': pi,
                              'source_color': color(mat), 'triangles': len(t)})
    return result, locators


def deviation(a, b):
    """Seven samples on EVERY triangle, both directions, in millimetres."""
    def one(g, target):
        p = target.reshape(-1, 3)
        t = np.arange(len(p)).reshape(-1, 3)
        gp = g.reshape(-1, 3)
        gt = np.arange(len(gp)).reshape(-1, 3)
        ds = distances(surface_samples(gp, gt).reshape(-1, 3), p, t)
        return {'max_mm': float(ds.max()), 'p99_mm': float(np.percentile(ds, 99)), 'samples': len(ds)}
    return {'forward': one(a, b), 'reverse': one(b, a)}


def upper_source_map(component):
    """Resolve fixed native ordinals without pretending they are source STEP IDs."""
    from cad_document import CadDocument
    folder = ROOT / 'out/rmuc2027-equipment-pipeline' / component['id']
    z = np.load(folder / 'native.npz')
    p, t, u = (z[k] for k in ['positions_mm', 'triangles', 'unit_ids'])
    boxes = {int(i): np.array([p[t[u == i]].min((0, 1)), p[t[u == i]].max((0, 1))]) for i in np.unique(u)}
    rows = []
    with CadDocument.from_step(folder / 'source.step', workers=1, intern_layers=True) as cad:
        for kind, ids in [('body', component['solid_body_ids']),
                          ('shell', [s for ids in component['shell_ids_by_body'].values() for s in ids])]:
            for sid in ids:
                row = cad.index.r(component['export_body_ids'][str(sid)]) if kind == 'body' else cad.index.r(sid)
                lo, hi, _ = cad.model.body_bbox(row)
                candidates = sorted((float(np.max(abs(box - [lo, hi]))), i) for i, box in boxes.items())
                assert candidates[0][0] < 10 and candidates[1][0] - candidates[0][0] > .05
                rows.append({'source_kind': kind, 'source_id': sid, 'native_unit': candidates[0][1],
                             'vertex_bbox_vs_native_max_delta_mm': candidates[0][0],
                             'second_candidate_delta_mm': candidates[1][0]})
    dump('upper-source-map.json', {'method': 'Unique nearest source vertex bbox vs native tessellation bbox; not a transferred face-identity proof. All additional native units retained by whole component guard.', 'mappings': rows})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'source/RMUC2027_V1.0.0.stp'
    assert digest(source) == SHA
    hpath = ROOT / 'out/rmuc2027-hierarchy/hierarchy.json'
    h = json.loads(hpath.read_text())
    assert h['source_sha256'] == SHA and h['source_geometry_preserved']
    assert digest(hpath.parent / 'field.step') == h['files_sha256']['field.step']
    inputs = {str(source.relative_to(ROOT)): SHA, str(hpath.relative_to(ROOT)): digest(hpath)}
    installed_before = {str(p): digest(p) for p in PKG.rglob('*.glb')}
    plan_path = ROOT / 'benchmarks/2026-10-23-feature-investigation/plan.json'
    inputs[str(plan_path.relative_to(ROOT))] = digest(plan_path)
    plan = json.loads(plan_path.read_text())
    combined = next(l for l in plan['levels'] if l['id'] == 'combined-visual')['files']
    assets = {}
    all_data = {}
    for asset, rel in [('base', 'equipment/base.glb'), ('outpost', 'outpost.glb'), ('arena-static', 'arena-static.glb')]:
        paths = {'installed': PKG / rel,
                 'refined1mm': ROOT / 'out/rmuc2027-runtime-opportunities/refined/visual-1mm' / Path(rel).name,
                 'combined17mm': ROOT / combined[asset]['path']}
        assert digest(paths['combined17mm']) == combined[asset]['sha256']
        data = {}
        loc = {}
        for level, path in paths.items():
            data[level], loc[level] = load_glb(path)
            inputs[str(path)] = digest(path)
        keys = sorted(set().union(*(set(v) for v in data.values())))
        rows = {}
        for key in keys:
            if asset == 'arena-static' and not key.startswith('dart-station'):
                continue
            levels = {level: summary(parts[key]) for level, parts in data.items() if key in parts}
            rows[key] = {'levels': levels, 'locators': {level: loc[level].get(key, []) for level in loc}}
            if all(level in levels for level in paths):
                rows[key]['installed_to_refined_changed'] = levels['installed']['geometry_material_multiset_sha256'] != levels['refined1mm']['geometry_material_multiset_sha256']
                rows[key]['refined_to_combined_changed'] = levels['refined1mm']['geometry_material_multiset_sha256'] != levels['combined17mm']['geometry_material_multiset_sha256']
        assets[asset] = {'paths': {k: str(v) for k, v in paths.items()}, 'parts': rows}
        all_data[asset] = data

    native_folder = OUT / 'native-base'
    audit = json.loads((native_folder / 'audit.json').read_text())
    for name, expected in audit['outputs_sha256'].items():
        assert digest(native_folder / name) == expected
    assert audit['hierarchy_sha256'] == digest(hpath)
    z = np.load(native_folder / 'geometry.npz')
    native_base = {u['source_id']: z['positions_mm'][z['triangles'][z['unit_ids'] == i]]
                   for i, u in enumerate(audit['units'])}
    base_native = {}
    # Include every Base solid plus its explicit original surface-shell IDs.
    for i, unit in enumerate(audit['units']):
        u = {k: v for k, v in unit.items() if k != 'face_ids'}
        u['face_ids_sha256'] = hashlib.sha256(json.dumps(unit['face_ids']).encode()).hexdigest()
        u['color_triangles'] = dict(defaultdict(int))
        for f in audit['faces']:
            if f['unit'] == i:
                c = str(f['source_colour'])
                u['color_triangles'][c] = u['color_triangles'].get(c, 0) + f['triangles']
        base_native[str(unit['source_id'])] = u

    # Source modules contain neutral housing and shells as well as colored optics.
    scopes = []
    for i, body in enumerate(SCREENS):
        members = [body, BASE_SIDE_LIGHTS[i], BASE_SHELLS[i], *BASE_SMALL_SHELLS[i]]
        scopes.append({'id': f'base.armor.{i}', 'asset': 'base', 'component_id': 'base/source-model',
                       'source_product_id': 4774244, 'source_body_ids': members[:2], 'source_shell_ids': members[2:],
                       'runtime_keys': [f'base/source-model|{sid}' for sid in members],
                       'confidence': 'geometry-matched front body, complementary side light, neutral housing shell and ten enclosed/corner hardware shells; shared carrier brackets recorded separately; physical grouping inferred from source bounds and isolated geometry, not an authored functional assembly'})
    for i in range(3):
        cid = f'outpost/rotor/module-{i}'
        c = next(c for c in h['components'] if c['id'] == cid)
        folder = ROOT / 'out/rmuc2027-equipment-pipeline' / cid
        j = json.loads((folder / 'native.json').read_text())
        nz = np.load(folder / 'native.npz')
        assert digest(folder / 'native.npz') == j['native_npz_sha256']
        assert digest(folder / 'source.step') == j['source_step_sha256']
        for name in ['native.npz', 'source.step', 'native.json', 'native.glb']:
            inputs[str((folder / name).relative_to(ROOT))] = digest(folder / name)
        shells = [s for ids in c['shell_ids_by_body'].values() for s in ids]
        ids = c['solid_body_ids'] + shells
        scopes.append({'id': cid, 'asset': 'outpost', 'component_id': cid, 'source_product_id': 2603236,
                       'source_body_ids': c['solid_body_ids'], 'source_shell_ids': shells,
                       'runtime_keys': [f'{cid}|{sid}' for sid in ids], 'source_faces': c['face_count'],
                       'native_triangles': len(nz['triangles']),
                       'confidence': 'complete hierarchy work partition: five solids AND one neutral shell'})

    # Functional attribution is provisional for dart target; keep complete neutral context.
    for label, bodies in [('base.dart-target.context', [4072376, 4077428, 4558565, 4568881, 4570891]),
                          ('base.carrier-brackets.context', [4549040, 4553014, 4556988]),
                          ('base.shields.occluders', SHIELDS)]:
        scopes.append({'id': label, 'asset': 'base', 'component_id': 'base/source-model', 'source_product_id': 4774244,
                       'source_body_ids': bodies, 'source_shell_ids': [], 'runtime_keys': [f'base/source-model|{s}' for s in bodies],
                       'confidence': 'context guard; not a claim that these are scoring Armor Modules'})
    dart = next(s for s in scopes if s['id'] == 'base.dart-target.context')
    dart['source_shell_ids'] = [4756187]
    dart['runtime_keys'].append('base/source-model|4756187')
    cid = 'outpost/fixed/upper-cluster'
    c = next(c for c in h['components'] if c['id'] == cid)
    upper_source_map(c)
    folder = ROOT / 'out/rmuc2027-equipment-pipeline' / cid
    for name in ['source.step', 'native.npz', 'native.json', 'native.glb']:
        inputs[str((folder / name).relative_to(ROOT))] = digest(folder / name)
    scopes.append({'id': 'outpost.dart-target.context', 'asset': 'outpost', 'component_id': cid,
                   'source_product_id': c['source_product_id'], 'source_body_ids': c['solid_body_ids'],
                   'source_shell_ids': [s for ids in c['shell_ids_by_body'].values() for s in ids],
                   'runtime_keys': sorted(k for k in assets['outpost']['parts'] if k.startswith(cid + '|')),
                   'confidence': 'whole upper-cluster guard pending precise shared-body functional attribution; includes dart detector and guiding optic'})

    for s in scopes:
        rows = assets[s['asset']]['parts']
        assert all(k in rows for k in s['runtime_keys'])
        s['triangle_counts'] = {level: sum(rows[k]['levels'][level]['triangles'] for k in s['runtime_keys'])
                                for level in ['installed', 'refined1mm', 'combined17mm']}
        s['changed_installed_to_refined'] = [k for k in s['runtime_keys'] if rows[k]['installed_to_refined_changed']]
        s['changed_refined_to_combined'] = [k for k in s['runtime_keys'] if rows[k]['refined_to_combined_changed']]
        if s['asset'] == 'base':
            s['native_triangles'] = sum(base_native[str(i)]['triangles'] for i in s['source_body_ids'] + s['source_shell_ids'])
        # Focus expensive dense shape checks on the six actual Armor Modules.
        if s['id'].startswith('base.armor.'):
            native = np.concatenate([native_base[sid] for sid in s['source_body_ids'] + s['source_shell_ids']])
        elif s['id'].startswith('outpost/rotor/'):
            nz = np.load(ROOT / 'out/rmuc2027-equipment-pipeline' / s['component_id'] / 'native.npz')
            native = nz['positions_mm'][nz['triangles']]
        else:
            continue
        s['native_vs_visual_sampled_shape'] = {}
        s['visual_step_sampled_shape'] = {}
        cache = {}
        for level in ['installed', 'refined1mm', 'combined17mm']:
            parts = [piece for key in s['runtime_keys'] for piece in all_data[s['asset']][level][key]]
            sig = summary(parts)['geometry_material_multiset_sha256']
            if sig not in cache:
                cache[sig] = deviation(native, np.concatenate([g for g, _ in parts]))
            s['native_vs_visual_sampled_shape'][level] = cache[sig]
        for before, after in [('installed', 'refined1mm'), ('refined1mm', 'combined17mm')]:
            def geometry(level):
                return np.concatenate([g for key in s['runtime_keys'] for g, _ in all_data[s['asset']][level][key]])
            s['visual_step_sampled_shape'][before + '_to_' + after] = deviation(geometry(before), geometry(after))
        if s['asset'] == 'base':
            from export_field_package import GlbWriter
            ref = OUT / 'native-modules' / (s['id'] + '.glb')
            ref.parent.mkdir(exist_ok=True)
            writer = GlbWriter(s['id'], {'source_sha256': SHA, 'source_native_reference': True})
            for sid in s['source_body_ids'] + s['source_shell_ids']:
                unit_index = next(i for i, u in enumerate(audit['units']) if u['source_id'] == sid)
                selected = z['unit_ids'] == unit_index
                palette = z['source_srgb']
                colors = [','.join(f'{v:.4f}' for v in palette[int(ci)]) for ci in z['colour_indices'][selected]]
                writer.add_node(f'source_unit_{sid}', z['positions_mm'] / 1000, z['triangles'][selected], colors)
            writer.write(ref)
            s['native_reference'] = str(ref.relative_to(ROOT))
        else:
            s['native_reference'] = str((ROOT / 'out/rmuc2027-equipment-pipeline' / s['component_id'] / 'native.glb').relative_to(ROOT))
        print(s['id'], s['triangle_counts'], flush=True)

    # AABB guard is deliberately inclusive. It records candidates, never semantic membership.
    neighbors = {}
    for body in SCREENS + [4077428]:
        box = np.array(base_native[str(body)]['bbox_mm'])
        candidates = []
        for sid, unit in base_native.items():
            other = np.array(unit['bbox_mm'])
            gap = np.maximum(np.maximum(box[0] - other[1], other[0] - box[1]), 0)
            if np.linalg.norm(gap) <= 8 and int(sid) != body:
                candidates.append(int(sid))
        neighbors[str(body)] = candidates

    assert installed_before == {str(p): digest(p) for p in PKG.rglob('*.glb')}
    dump('audit.json', {'source_sha256': SHA, 'hierarchy_geometry_record_sha256': h['geometry_record_sha256'],
         'inputs_sha256': inputs, 'installed_unchanged': True, 'scopes': scopes, 'assets': assets,
         'base_source_units': base_native, 'base_8mm_aabb_context_candidates': neighbors,
         'method': 'Live placed GLB triangles per definition asset, millimetres; material JSON and triangle geometry multiset at 0.000001mm. Source native Base 0.4mm/0.25rad; Outpost existing native cache. Dense seven samples per triangle both directions, uncolored full-module surfaces. Finite checks are not continuous CAD/optical equivalence proofs.'})
    dump('summary.json', {'source_sha256': SHA, 'installed_unchanged': True,
                          'scopes': scopes, 'base_8mm_aabb_context_candidates': neighbors})


if __name__ == '__main__':
    main()
