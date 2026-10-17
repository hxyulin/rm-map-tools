#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose approved definitions and replay mounting edits before shell LOD.

DJI / RoboMaster owns source geometry and appearance. This produces a new visual
candidate, retaining every hierarchy occurrence; no runtime/collision change.
"""
import argparse
import collections
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_pass_composition import compose_shells
from cad_local_lod import guarded_vertex_lod, planar_outline_vertices
from cad_planar_shell import planar_skin
from cad_wall_fill import shape_map
from gltf_scene import read_glb, mesh_instances
from mesh_parts import tessellate
from mesh_quality import deviation, distances
from plan_cad_lods import build_plan, digest
from validate_parts import read_part
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def read(path):
    return json.loads(path.read_bytes())


def count(path):
    doc, blob = read_glb(path)
    return sum(len(t) for _, _, _, t, _ in mesh_instances(doc, blob))


def native(source):
    doc, reader, error = read_part(str(source))
    if error: raise ValueError(error)
    roots = Sequence_TDF_Label()
    XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots)
    if roots.Length() != 1: raise ValueError('ambiguous native root')
    root = XCAFDoc_ShapeTool.GetShape_s(roots.Value(1))
    faces, shells = shape_map(root, TopAbs_FACE), shape_map(root, TopAbs_SHELL)
    owner = {}
    for unit in range(1, shells.Extent() + 1):
        local = shape_map(shells.FindKey(unit), TopAbs_FACE)
        for j in range(1, local.Extent() + 1):
            fi = faces.FindIndex(local.FindKey(j))
            if fi in owner: raise ValueError('ambiguous shell ownership')
            owner[fi] = unit
    for fi in range(1, faces.Extent() + 1): owner.setdefault(fi, -fi)
    return doc, reader, faces, shells, owner


def replayer(cid, shells, palette, whole_source):
    protected = [i for i, c in enumerate(palette)
                 if c is None or np.ptp(list(map(float, c.split(',')))) > .1]
    chromatic = [i for i, c in enumerate(palette)
                 if c is not None and np.ptp(list(map(float, c.split(',')))) > .1]
    coloured = whole_source['triangles'][np.isin(whole_source['material_ids'], chromatic)]
    def replay(unit, p, t, m):
        if len(t) < 128: return p, t, m, {'operation': 'retain-small-edited-source'}
        structural = unit == 1 and cid in ['dart-station/frame', 'outpost/fixed/upper-cluster']
        rune = cid.startswith('rune/')
        small = np.ptp(p, axis=0).max() <= 17
        limit = (0.4 if small else 3) if rune else (3 if structural else 1)
        nominal = (.15 if small else 1) if rune else (1 if structural else .25)
        p1, t1, m1, skin = planar_skin(p, t, m, protected_material_ids=protected)
        locks = set(np.unique(t1[np.isin(m1, protected)]).tolist())
        if unit > 0:
            outline, _ = planar_outline_vertices(shells.FindKey(unit), minimum_face_area_mm2=20000 if structural else 5000,
                                                 corner_turn_rad=math.radians(15) if structural else 0)
            if len(outline):
                from scipy.spatial import cKDTree
                tree = cKDTree(p1); distance, nearest = tree.query(outline)
                locks.update(map(int, nearest[distance <= .01]))
                for v in outline[distance > .01]:
                    locks.update(map(int, np.atleast_1d(tree.query(v, k=min(8, len(p1)))[1])))
        margin = 3 if structural and cid.startswith('outpost/') else (5 if rune and not small else 0)
        if margin and len(coloured):
            locks.update(np.flatnonzero(distances(p1, whole_source['positions_mm'], coloured) <= margin).tolist())
        attempts = []
        for metric in [nominal, nominal / 2, nominal / 4]:
            q, f, k, guard = guarded_vertex_lod(p1, t1, m1, error_mm=metric, sampled_limit_mm=limit,
                                               sample_count=8192, maximum_iterations=8,
                                               protected_vertex_indices=np.array(sorted(locks), dtype=np.int64))
            keep = ~np.isin(k, protected); original = np.isin(m, protected)
            f = np.concatenate([f[keep], t[original] + len(q)])
            k = np.r_[k[keep], m[original]]; q = np.concatenate([q, p])
            quality = deviation(p, t, q, f, count=16384)
            attempts.append({'nominal_mm': metric, 'triangles': len(f), 'sampled_deviation_mm': quality})
            if quality['max'] <= limit + .001: break
        else:
            q, f, k = p1, t1, m1
            quality = deviation(p, t, q, f, count=16384)
            if quality['max'] > limit + .001: q, f, k = p, t, m
        if len(f) > len(t): q, f, k = p, t, m
        for key in protected:
            old = p[t[m == key]].reshape(-1, 9); new = q[f[k == key]].reshape(-1, 9)
            if sorted(map(tuple, old)) != sorted(map(tuple, new)):
                raise ValueError('edited-source protected paint geometry changed')
        quality = deviation(p, t, q, f, count=16384)
        if quality['max'] > limit + .001: raise ValueError('final edited-source distance guard failed')
        return q, f, k, {'input': 'edited original native tessellation', 'nominal_mm': nominal,
                         'sampled_limit_mm': limit, 'colour_margin_mm': margin,
                         'sampled_deviation_mm': quality, 'attempts': attempts,
                         'protected_material_ids': protected, 'protected_triangles_exact': True,
                         'planar_patches': sum(r['operation'] == 'planar-boundary-skin' for r in skin['patches'])}
    return replay


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True); ap.add_argument('--id')
    args = ap.parse_args(); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    pipeline_dir = ROOT / 'out/rmuc2027-equipment-pipeline'
    hp = ROOT / 'out/rmuc2027-hierarchy/hierarchy.json'; hierarchy = read(hp)
    inventory = read(pipeline_dir / 'inventory.json')
    if inventory['hierarchy_sha256'] != digest(hp): raise ValueError('inventory hierarchy changed')
    plan = build_plan(hierarchy)
    uses = collections.Counter(n['component_id'] for n in plan['nodes'] if n['component_id'])
    mounts = ROOT / 'out/rmuc2027-mounting-native'
    mounting = {c['id']: c for c in read(mounts / 'summary.json')['components'] if not c['id'].startswith('complete/')}
    rune_dir = ROOT / 'out/rmuc2027-rune-front'
    rune = {c['id']: c for c in read(rune_dir / 'summary.json')['components']}
    structural_dir = ROOT / 'out/rmuc2027-equipment-structure-final'
    structural = {c['id']: c for c in read(structural_dir / 'summary.json')['components']}
    walls_dir = ROOT / 'out/rmuc2027-wall-fill-final'
    walls = {c['component_id']: c for c in read(walls_dir / 'summary.json')['components']}
    terrain_dir = ROOT / 'out/rmuc2027-terrain-cost-full'
    terrain = {c['id']: c for c in read(terrain_dir / 'audit.json')['components']}
    pipeline = module('pipeline', ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py')
    helpers = [Path(__file__), ROOT / 'python/cad_pass_composition.py', ROOT / 'python/cad_local_lod.py',
               ROOT / 'python/cad_planar_shell.py', ROOT / 'python/mesh_parts.py', ROOT / 'python/mesh_quality.py',
               ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py']
    producers = {str(p.relative_to(ROOT)): digest(p) for p in helpers}
    rows = []
    for item in inventory['components']:
        cid = item['id']
        if args.id and cid != args.id: continue
        folder = out / cid; folder.mkdir(parents=True, exist_ok=True)
        source = pipeline_dir / cid / 'source.step'
        if digest(source) != item['source_step_sha256']: raise ValueError('work-part source changed')
        dependencies = {str(source.relative_to(ROOT)): digest(source), str(hp.relative_to(ROOT)): digest(hp)}
        reference_npz = None; policy = 'generic-shell-lod' if item['selected'] else 'native-terrain'
        priority = False
        if cid == 'base/source-model':
            ledger = ROOT / 'out/rmuc2027-base-textures-final/composition.json'
            reference = ledger.with_name('base-visual.glb'); expected = read(ledger)['base_glb_sha256']
            policy = 'specialized-base-panels-lights-texture'; priority = True
        elif cid in walls:
            ledger = walls_dir / 'summary.json'; reference = walls_dir / cid.split('/')[0] / 'candidate.glb'
            expected = walls[cid]['after']['sha256']; policy = 'specialized-wall-fill'; priority = True
        elif cid == 'fan/body-2717086':
            ledger = ROOT / 'out/rmuc2027-fan-proxy/summary.json'; reference = ledger.with_name('fan-proxy.glb')
            expected = read(ledger)['outputs_sha256']['fan-proxy.glb']; policy = 'specialized-fan-duct'; priority = True
        elif cid in rune:
            ledger = rune_dir / 'summary.json'; reference_npz = rune_dir / cid / 'candidate.npz'
            reference = reference_npz.with_suffix('.glb'); expected = rune[cid]['outputs_sha256']['candidate.glb']
            policy = 'rune-front-back-skins' if '/arm-' in cid else 'rune-selective-lod'
            priority = '/arm-' in cid
        elif cid in structural:
            ledger = structural_dir / 'summary.json'; reference_npz = structural_dir / cid / 'candidate.npz'
            reference = reference_npz.with_suffix('.glb'); expected = structural[cid]['outputs_sha256']['candidate.glb']
            policy = 'structural-shell-lod'
        elif item['selected']:
            ledger = pipeline_dir / cid / 'passes.json'; reference_npz = ledger.with_name('lod.npz')
            reference = reference_npz.with_suffix('.glb'); expected = read(ledger)['outputs_sha256']['lod.glb']
        else:
            ledger = terrain_dir / 'audit.json'; reference = terrain_dir / cid / 'visual.glb'
            expected = terrain[cid]['visual_sha256']
        if digest(reference) != expected: raise ValueError('approved reference changed: ' + cid)
        for path in [reference, ledger] + ([reference_npz] if reference_npz else []):
            dependencies[str(path.relative_to(ROOT))] = digest(path)
        mount = mounting.get(cid)
        if mount:
            if mount['source_step_sha256'] != item['source_step_sha256']: raise ValueError('mounting source mismatch')
            for path in [mounts / cid / 'summary.json', mounts / cid / 'combined.npz',
                         mounts / cid / 'combined-native-face-indices.npy']:
                dependencies[str(path.relative_to(ROOT))] = digest(path)
            for name, sha in mount['stages']['combined']['outputs_sha256'].items():
                if digest(mounts / cid / name) != sha: raise ValueError('mounting output changed')
        cavity = cid == 'energy-unit/unit'
        if cavity:
            ledger = ROOT / 'out/rmuc2027-equipment-opportunities/cavities.json'
            proof = next(c for c in read(ledger)['components'] if c['id'] == cid)
            if proof['source_step_sha256'] != item['source_step_sha256'] or not proof['checks'][0]['accepted'] or proof['checks'][0]['removed_native_shell_indices'] != [2]:
                raise ValueError('cavity proof not qualified')
            dependencies[str(ledger.relative_to(ROOT))] = digest(ledger)
        cache = folder / 'summary.json'
        if cache.exists():
            record = read(cache)
            if record['dependencies_sha256'] != dependencies or record['producer_sha256'] != producers: raise ValueError('stale composed cache: ' + cid)
            if digest(ROOT / record['candidate_glb']) != record['candidate_sha256']: raise ValueError('cached composed GLB changed')
            rows.append(record); print('cached', cid, flush=True); continue
        before = count(reference); candidate = reference; replay_records = []; changed = set()
        superseded = bool(priority and mount)
        if (mount and not priority) or cavity:
            doc, reader, faces, shells, owner = native(source)
            if faces.Extent() != item['source_faces']: raise ValueError('native ordinal domain changed')
            if reference_npz:
                reference_data = dict(np.load(reference_npz))
            else:
                observed = []; stats = {}
                p, t, m, palette = tessellate(doc, .4, .25, stats, lambda i, f, n: observed.extend([owner[faces.FindIndex(f)]] * n))
                if stats.get('unmeshed_faces') or len(t) != item['native_triangles'] or len(t) != before: raise ValueError('native terrain reference mismatch')
                reference_data = dict(positions_mm=p, triangles=t, material_ids=m, unit_ids=np.array(observed), palette=np.array([c or '' for c in palette]))
            palette = [c or None for c in reference_data['palette'].tolist()]
            if mount:
                edited = dict(np.load(mounts / cid / 'combined.npz'))
                native_faces = np.load(mounts / cid / 'combined-native-face-indices.npy')
                edited['unit_ids'] = np.array([owner[abs(int(fi))] for fi in native_faces])
                remap = np.array([palette.index(c or None) for c in edited['palette'].tolist()])
                edited['material_ids'] = remap[edited['material_ids']]
                proof = mount['stages']['combined']['proof']
                changed = {owner[int(fi)] for fi in proof['removed_native_faces']}
                changed.update(owner[r['source_native_face_index']] for r in proof['rebuilt_faces'])
            else: edited = reference_data
            p, t, m, u, replay_records = compose_shells(reference_data, edited, changed,
                                                        replayer(cid, shells, palette, edited), omit_units=[2] if cavity else [])
            pipeline.save_mesh(folder, 'candidate', p, t, m, palette, u)
            candidate = folder / 'candidate.glb'
            # Directly validate all untouched approved shells, including exported normals/materials.
            attributes = module('attributes', ROOT / 'benchmarks/2026-10-17-equipment-structure/review.py')
            attribute_reference = reference
            if reference_npz is None:
                # Restored terrain GLBs have no shell extras. Re-export the same
                # native arrays with shell ownership and verify aggregate payloads.
                pipeline.save_mesh(folder, 'reference-shells', reference_data['positions_mm'],
                                   reference_data['triangles'], reference_data['material_ids'],
                                   palette, reference_data['unit_ids'])
                attribute_reference = folder / 'reference-shells.glb'
                def aggregate(path):
                    from gltf_scene import accessor
                    d, b = read_glb(path); grouped = collections.defaultdict(list)
                    for node in d['nodes']:
                        if 'mesh' not in node: continue
                        for primitive in d['meshes'][node['mesh']]['primitives']:
                            indices = accessor(d, b, primitive['indices']).reshape(-1, 3)
                            position = accessor(d, b, primitive['attributes']['POSITION'])[indices]
                            normal = accessor(d, b, primitive['attributes']['NORMAL'])[indices]
                            key = json.dumps(d['materials'][primitive['material']], sort_keys=True)
                            packed = np.ascontiguousarray(np.c_[position.reshape(-1, 9), normal.reshape(-1, 9)])
                            grouped[key].append(packed.view(np.dtype((np.void, packed.dtype.itemsize * 18))).ravel())
                    return {key: np.sort(np.concatenate(value)) for key, value in grouped.items()}
                original_attributes, grouped_attributes = aggregate(reference), aggregate(attribute_reference)
                if original_attributes.keys() != grouped_attributes.keys() or any(not np.array_equal(original_attributes[k], grouped_attributes[k]) for k in original_attributes):
                    raise ValueError('regrouped native reference attributes changed')
            old, new = attributes.payload(attribute_reference), attributes.payload(candidate)
            exact_units = set(map(int, reference_data['unit_ids'])) - changed - ({2} if cavity else set())
            for unit in exact_units:
                if unit not in old or unit not in new or old[unit].keys() != new[unit].keys(): raise ValueError('untouched shell material membership changed')
                for key in old[unit]:
                    if not np.array_equal(old[unit][key][0], new[unit][key][0]) or old[unit][key][1] != new[unit][key][1]:
                        raise ValueError('untouched shell exported attributes changed')
        after = count(candidate)
        record = {'id': cid, 'uses': uses[cid], 'source_step_sha256': item['source_step_sha256'],
                  'reference_glb': str(reference.relative_to(ROOT)), 'reference_sha256': digest(reference),
                  'candidate_glb': str(candidate.relative_to(ROOT)), 'candidate_sha256': digest(candidate),
                  'reference_triangles': before, 'candidate_triangles': after,
                  'placed_triangles': after * uses[cid], 'placed_saving': (before - after) * uses[cid],
                  'policy': policy, 'mounting_superseded_by_specialized_component': superseded,
                  'mounting_changed_shells': sorted(changed), 'cavity_shell_omitted': 2 if cavity else None,
                  'shell_operations': replay_records, 'dependencies_sha256': dependencies, 'producer_sha256': producers}
        cache.write_text(json.dumps(record, indent=2) + '\n'); rows.append(record)
        print(cid, before, '->', after, 'changed shells', len(changed), 'special override', superseded, flush=True)
    report = {'schema': 'rm-composed-visual-pipeline-v1', 'hierarchy_sha256': digest(hp),
              'source_sha256': hierarchy['files_sha256']['field.step'], 'components': rows,
              'definitions': len(rows), 'placed_uses': sum(r['uses'] for r in rows),
              'reference_placed_triangles': sum(r['reference_triangles'] * r['uses'] for r in rows),
              'candidate_placed_triangles': sum(r['placed_triangles'] for r in rows),
              'placed_saving': sum(r['placed_saving'] for r in rows), 'producer_sha256': producers,
              'complete': not bool(args.id),
              'scope': 'Specialized component overrides > source-bound mounting edits > per-shell LOD. Unchanged shells reuse approved attributes exactly. Source/hierarchy and every occurrence retained. Qualified Energy cavity omitted. Road 16-section preview excluded until a complete road mesh exists. New composed visual candidate; no runtime installation, detector or collision changes.'}
    if not args.id and (len(rows) != 116 or report['placed_uses'] != 171 or report['reference_placed_triangles'] != 2343812):
        raise ValueError('complete approved baseline accounting mismatch: ' + str(report['reference_placed_triangles']))
    (out / ('summary.json' if not args.id else 'partial-summary.json')).write_text(json.dumps(report, indent=2) + '\n')
    print({k: report[k] for k in ['definitions', 'placed_uses', 'reference_placed_triangles', 'candidate_placed_triangles', 'placed_saving']}, flush=True)

if __name__ == '__main__': main()
