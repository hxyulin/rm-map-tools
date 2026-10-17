#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Replace the Energy stop interior with a rim-matched prism and count the field.

DJI / RoboMaster owns source geometry and appearance. Inspection artifacts only.
The exterior's complete vertex attributes/materials stay exact; no runtime edit.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from gltf_scene import read_glb, write_glb, accessor, mesh_instances, scene_nodes
from cad_glb_composition import RigidComposer
from cad_collision_profiles import prism_mesh
from cad_collision_roles import CollisionRoles
from export_field_package import GlbWriter
from simplify_package import compact
from mesh_quality import deviation
from plan_cad_lods import digest
from scipy.spatial import ConvexHull


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


def counts(path):
    d, b = read_glb(path); uses = [d['nodes'][i]['mesh'] for i, _, _ in scene_nodes(d) if 'mesh' in d['nodes'][i]]
    size = lambda i: sum(d['accessors'][p['indices']]['count'] // 3 for p in d['meshes'][i]['primitives'])
    return {'placed_triangles': sum(size(i) for i in uses), 'stored_triangles': sum(size(i) for i in range(len(d['meshes']))),
            'referenced_unique_triangles': sum(size(i) for i in set(uses)), 'mesh_definitions': len(d['meshes']),
            'referenced_mesh_definitions': len(set(uses)), 'primitive_definitions': sum(len(m['primitives']) for m in d['meshes']), 'bytes': path.stat().st_size}


def visual_prism(source, out):
    before, blob = read_glb(source); changed = copy.deepcopy(before); removed = []; retained = []; material = None; ring = None
    for node in before['nodes']:
        if 'mesh' in node and any(k in node for k in ['matrix', 'translation', 'rotation', 'scale']): raise ValueError('expected baked source member')
    for mi, mesh in enumerate(before['meshes']):
        keep = []
        for prim in mesh['primitives']:
            p = accessor(before, blob, prim['attributes']['POSITION']); t = accessor(before, blob, prim['indices']).reshape(-1, 3); g = p[t].astype(float) * 1000
            source_color = before['materials'][prim['material']]['extras']['step_colour_srgb']
            if source_color is None:
                r = np.linalg.norm(g[:, :, [0, 2]], axis=2)
                if len(t) != 1744 or r.max() > 17.701 or g[:, :, 1].min() < 99.999 or g[:, :, 1].max() > 103.001: raise ValueError('source-bound interior selection changed')
                if material is not None: raise ValueError('interior primitive is ambiguous')
                material = prim['material']; removed.append(g)
                pp = p.astype(float) * 1000; mask = (abs(pp[:, 1] - 100) < .001) & (abs(np.linalg.norm(pp[:, [0, 2]], axis=1) - 17.7) < .001)
                ring = np.unique(pp[mask], axis=0)
                ring = ring[np.argsort(np.arctan2(ring[:, 2], ring[:, 0]))]
            else:
                keep.append(copy.deepcopy(prim)); retained.append((mi, copy.deepcopy(prim)))
        changed['meshes'][mi]['primitives'] = keep
    if material is None or len(ring) != 22: raise ValueError('source stop rim binding changed')
    q, f, topology = prism_mesh([{'outer': True, 'points_mm': ring}], [0, -1, 0], 3)
    proxy = out / 'stop-prism.glb'; writer = GlbWriter('energy-stop-prism', {'version': '2.0', 'copyright': 'DJI / RoboMaster source perimeter; derived interior visual prism'})
    writer.add_node('energy-stop-prism', q / 1000, f, [None] * len(f), extras={'derived_geometry': True, 'visual_only': True, 'source_native_shell_index': 1, 'native_identity_claim': False})
    writer.write(proxy); pd, pb = read_glb(proxy)
    if any('Texture' in k for k in before['materials'][material].get('pbrMetallicRoughness', {})): raise ValueError('textured stop requires a different binding')
    pd['materials'][0] = copy.deepcopy(before['materials'][material])
    composer = RigidComposer(); composer.append_definition('retained-energy', changed, blob); composer.append_definition('stop', pd, pb)
    composer.document['nodes'].append({'name': 'energy-interior-inspection', 'children': [], 'extras': {'inspection_only': True}}); composer.document['scenes'][0]['nodes'] = [0]
    composer.instantiate('retained-energy', 0); composer.instantiate('stop', 0)
    # Reuse the exact original fallback material; do not add a duplicate draw material.
    composer.document['meshes'][-1]['primitives'][0]['material'] = material; composer.document['materials'].pop()
    packed = compact(composer.document, composer.binary); target = out / 'energy-visual.glb'; write_glb(target, composer.document, packed)
    actual, data = read_glb(target); exact = 0
    for mi, prim in retained:
        found = [p for p in actual['meshes'][mi]['primitives'] if p['material'] == prim['material']]
        if len(found) != 1: raise ValueError('retained material region changed')
        now = found[0]
        if before['materials'][prim['material']] != actual['materials'][now['material']]: raise ValueError('retained PBR material changed')
        for key, index in prim['attributes'].items():
            if not np.array_equal(accessor(before, blob, index), accessor(actual, data, now['attributes'][key])): raise ValueError('exterior vertex attribute changed')
        if not np.array_equal(accessor(before, blob, prim['indices']), accessor(actual, data, now['indices'])): raise ValueError('exterior indices changed')
        exact += before['accessors'][prim['indices']]['count'] // 3
    if exact != 9292: raise ValueError('retained source count changed')
    previous = np.concatenate(removed).reshape(-1, 3); old_t = np.arange(len(previous)).reshape(-1, 3)
    envelope = ConvexHull(np.unique(previous, axis=0)).equations
    outside = float(max(0, (q @ envelope[:, :3].T + envelope[:, 3]).max()))
    if outside > .001: raise ValueError('interior prism protrudes outside the old retainer envelope')
    result = {'source_glb_sha256': digest(source), 'candidate_glb_sha256': digest(target), 'source_triangles': 11036, 'removed_interior_triangles': len(old_t), 'prism_triangles': len(f), 'candidate_triangles': exact + len(f), 'exact_retained_exterior_and_bore_triangles': exact,
              'rim_vertices': len(ring), 'depth_mm': 3, 'topology': topology, 'maximum_source_envelope_protrusion_mm': outside, 'sampled_interior_deviation_mm': deviation(previous, old_t, q, f, count=len(old_t)), 'source_material_exact': True, 'scope': 'Only the source-bound neutral stop/retainer primitive changes. Mouth, bore walls, exterior positions/normals/materials/indices exact. New interior stop is a rim-matched closed prism; collision unchanged.'}
    if counts(target)['placed_triangles'] != result['candidate_triangles']: raise ValueError('new visual count differs')
    (out / 'interior-summary.json').write_text(json.dumps(result, indent=2) + '\n'); return result


def group(cid):
    for prefix, name in [('dart-station', 'Dart station'), ('outpost/', 'Outpost'), ('technology-core/', 'Tech Core'), ('base/', 'Base'), ('rune/', 'Rune'), ('energy-unit/', 'Energy units'), ('resource-area/', 'Resource area'), ('fan/', 'Fans')]:
        if cid.startswith(prefix): return name
    return 'Groundwork and fixtures'


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    prior_path = ROOT / 'out/rmuc2027-game-lods/composition.json'; prior = json.loads(prior_path.read_bytes()); source = next(r for r in prior['components'] if r['id'] == 'energy-unit/unit')
    if digest(ROOT / source['candidate_glb']) != source['candidate_sha256']: raise ValueError('approved Energy changed')
    interior = visual_prism(ROOT / source['candidate_glb'], out); rows = []
    for old in prior['components']:
        r = copy.deepcopy(old)
        for key in ['glb', 'sha256', 'triangles']: r['reference_' + key] = old['candidate_' + key]
        if r['id'] == 'energy-unit/unit': r.update(candidate_glb=str((out / 'energy-visual.glb').relative_to(ROOT)), candidate_sha256=interior['candidate_glb_sha256'], candidate_triangles=interior['candidate_triangles'], policy='rim-matched-interior-stop-prism')
        r['placed_triangles'] = r['candidate_triangles'] * r['uses']; rows.append(r)
    composition = {'complete': True, 'components': rows, 'source_sha256': prior['source_sha256'], 'hierarchy_sha256': prior['hierarchy_sha256'], 'reference_placed_triangles': sum(r['reference_triangles'] * r['uses'] for r in rows), 'candidate_placed_triangles': sum(r['placed_triangles'] for r in rows), 'prior_composition_sha256': digest(prior_path)}
    (out / 'composition.json').write_text(json.dumps(composition, indent=2) + '\n')
    assembly = module('assembly', ROOT / 'benchmarks/2026-10-17-composed-pipeline/assemble.py'); hp = ROOT / 'out/rmuc2027-hierarchy/hierarchy.json'
    if digest(hp) != composition['hierarchy_sha256']: raise ValueError('hierarchy changed')
    built = assembly.build(out, composition, json.loads(hp.read_bytes()), 'candidate')
    collision = {}; cp = ROOT / 'out/rmuc2027-collision-solids'; panels = json.loads((cp / 'panels-summary.json').read_bytes()); energy = json.loads((cp / 'energy-summary.json').read_bytes())
    for r in panels['components']: collision[r['id']] = (cp / r['id'] / 'panels.glb', r['outputs_sha256']['panels.glb'])
    e = next(r for r in energy['variants'] if r['stage'] == 'meridian-1-24'); collision[energy['id']] = (cp / energy['id'] / 'meridian-1-24.glb', e['outputs_sha256']['meridian-1-24.glb'])
    game = ROOT / 'out/rmuc2027-game-lods'; game_collision = json.loads((game / 'collision-summary.json').read_bytes())
    for r in game_collision['components']:
        if r['variant'] == 'contact-6mm' and r['id'] not in collision: collision[r['id']] = (game / r['id'] / 'contact-6mm.glb', r['collision_glb_sha256'])
    road = json.loads((game / 'summary.json').read_bytes())
    for r in road['components']:
        if '/shell-' in r['id']:
            v = next(v for v in r['variants'] if v['sections_per_wave'] == 12); collision[r['id']] = (game / r['id'] / 'sections-12.glb', v['glb_sha256'])
    base = ROOT / 'out/rmuc2027-base-gap-led-final/collision/visual.glb'; base_report = json.loads((base.parent.parent / 'summary.json').read_bytes()); base_expected = base_report['stages']['collision']
    if counts(base)['placed_triangles'] != 16857 or digest(base) != base_expected['visual_sha256']: raise ValueError('Base collider changed')
    collision['base/source-model'] = (base, base_expected['visual_sha256'])
    roles = CollisionRoles.read(ROOT / 'rules/roles-rmuc2027-terrain.json', hp); groups = {}; components = []
    for r in rows:
        cid = r['id']; path = ROOT / r['candidate_glb']
        if digest(path) != r['candidate_sha256']: raise ValueError('visual candidate changed')
        stats = counts(path)
        if stats['placed_triangles'] != r['candidate_triangles']: raise ValueError('definition count differs')
        if not roles.collision_enabled(cid): cc, method, cpath, csha = 0, 'visual-only marking', None, None
        elif cid in collision:
            cpath, csha = collision[cid]
            if digest(cpath) != csha: raise ValueError('collision candidate changed')
            cc, method = counts(cpath)['placed_triangles'], 'dedicated candidate'
        else: cc, method, cpath, csha = stats['placed_triangles'], 'visual-derived fallback', path, r['candidate_sha256']
        g = group(cid); record = {'id': cid, 'group': g, 'uses': r['uses'], 'visual_per_definition': stats['placed_triangles'], 'visual_placed': stats['placed_triangles'] * r['uses'], 'stored_triangles': stats['stored_triangles'], 'referenced_unique_triangles': stats['referenced_unique_triangles'], 'unreferenced_stored_triangles': stats['stored_triangles'] - stats['referenced_unique_triangles'], 'collision_budget_per_definition': cc, 'collision_budget_placed': cc * r['uses'], 'collision_method': method, 'collision_glb': str(cpath.relative_to(ROOT)) if cpath else None, 'collision_sha256': csha, 'visual_glb': r['candidate_glb'], 'visual_sha256': r['candidate_sha256']}
        components.append(record); aggregate = groups.setdefault(g, {'group': g, 'definitions': 0, 'uses': 0, 'visual_placed': 0, 'stored_triangles': 0, 'referenced_unique_triangles': 0, 'unreferenced_stored_triangles': 0, 'collision_budget_placed': 0, 'dedicated_collision_definitions': 0, 'fallback_collision_definitions': 0, 'visual_only_definitions': 0})
        aggregate['definitions'] += 1
        for key in ['uses', 'visual_placed', 'stored_triangles', 'referenced_unique_triangles', 'unreferenced_stored_triangles', 'collision_budget_placed']: aggregate[key] += record[key]
        aggregate[{'dedicated candidate': 'dedicated_collision_definitions', 'visual-derived fallback': 'fallback_collision_definitions', 'visual-only marking': 'visual_only_definitions'}[method]] += 1
    totals = {key: sum(r[key] for r in components) for key in ['uses', 'visual_placed', 'stored_triangles', 'referenced_unique_triangles', 'unreferenced_stored_triangles', 'collision_budget_placed']}
    actual = counts(out / 'candidate-field.glb')
    if totals['visual_placed'] != actual['placed_triangles'] or totals['stored_triangles'] != actual['stored_triangles'] or totals['referenced_unique_triangles'] != actual['referenced_unique_triangles']: raise ValueError('full arena accounting differs')
    report = {'totals': totals, 'groups': sorted(groups.values(), key=lambda r: -r['visual_placed']), 'components': sorted(components, key=lambda r: -r['visual_placed']), 'full_glb': actual, 'assembly': {k: v for k, v in built.items() if k != 'definitions'}, 'interior': interior, 'composition_sha256': digest(out / 'composition.json'), 'producer_sha256': digest(__file__), 'source_reports_sha256': {str(p.relative_to(ROOT)): digest(p) for p in [prior_path, cp / 'panels-summary.json', cp / 'energy-summary.json', game / 'collision-summary.json', ROOT / 'rules/roles-rmuc2027-terrain.json']},
              'collision_scope': 'Prospective full-map triangle budget: dedicated candidates where available, zero for whole visual-only markings, otherwise current visual geometry. Includes unbound moving equipment conservatively; not installed runtime colliders, detector counts or a physics capture.', 'scope': 'Complete 116-definition, 171-occurrence source-pose visual candidate. Placed counts include instances; stored and referenced-unique mesh counts reported separately. No runtime, scoring or collision replacement.'}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n'); print(json.dumps({'totals': totals, 'groups': report['groups'], 'interior': interior}, indent=2))


if __name__ == '__main__': main()
