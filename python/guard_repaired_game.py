#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Restore lost surface coverage before partitioning reviewed Low game assets."""
import argparse
import copy
from pathlib import Path
import tempfile
import numpy as np
from cad_surface_coverage import coverage_repair
from export_repaired_game import ROOT, dump
from gltf_scene import accessor, read_glb, write_glb, scene_nodes
from plan_cad_lods import digest
from simplify_package import append_accessor, compact, scene_triangles


def guard(out):
    out = Path(out).resolve()
    if out.exists(): raise ValueError('output exists')
    source = ROOT / 'out/rmuc2027-equipment-shells/candidate-field.glb'
    low = ROOT / 'out/rmuc2027-low-repair/budget-sealed-field.glb'
    import json
    report = json.loads((low.parent / 'budget-sealed.json').read_text())
    plan = json.loads((low.parent / 'seal-plan.json').read_text())
    if digest(low) != report['sha256'] or digest(source) != plan['source_sha256']:
        raise ValueError('coverage inputs changed')
    sd, sb = read_glb(source); ld, lb = read_glb(low)
    if sd['materials'] != ld['materials']: raise ValueError('source material tables differ')
    changed = copy.deepcopy(ld); blob = bytearray(lb); rows = []; expected = {}
    source_pairs = {(sd['nodes'][i]['mesh'], pi) for i, _, _ in scene_nodes(sd) if 'mesh' in sd['nodes'][i]
                    for pi in range(len(sd['meshes'][sd['nodes'][i]['mesh']]['primitives']))}
    checked = set(); checked_pieces = 0
    for mi, mesh in enumerate(ld['meshes']):
        for pi, prim in enumerate(mesh['primitives']):
            ex = prim['extras']; sm = ex['source_mesh_index']; sp = ex['source_primitive_index']
            if (sm, sp) in checked: raise ValueError('duplicate source primitive')
            checked.add((sm, sp))
            original = sd['meshes'][sm]['primitives'][sp]
            p = accessor(sd, sb, original['attributes']['POSITION'])
            t = accessor(sd, sb, original['indices']).reshape(-1, 3)
            q = accessor(ld, lb, prim['attributes']['POSITION'])
            f = accessor(ld, lb, prim['indices']).reshape(-1, 3)
            keep, restore, row = coverage_repair(p, t, q, f)
            checked_pieces += len(row['pieces'])
            if not restore.any(): continue
            if original['material'] != prim['material'] or original['attributes'].keys() != prim['attributes'].keys():
                raise ValueError('incompatible source surface attributes')
            output = np.concatenate([f[keep], t[restore] + len(q)])
            used, inv = np.unique(output, return_inverse=True)
            destination = changed['meshes'][mi]['primitives'][pi]
            values = {}
            for key, ai in prim['attributes'].items():
                source_ai = original['attributes'][key]; a = ld['accessors'][ai]; sa = sd['accessors'][source_ai]
                if any(a.get(k) != sa.get(k) for k in ['type', 'componentType', 'normalized']):
                    raise ValueError('source attribute encoding differs')
                value = np.concatenate([accessor(ld, lb, ai), accessor(sd, sb, source_ai)])[used]
                new = append_accessor(changed, blob, value, a['type'], a['componentType'])
                if a.get('normalized'): changed['accessors'][new]['normalized'] = True
                destination['attributes'][key] = new; values[key] = value
            destination['indices'] = append_accessor(changed, blob, inv.ravel().astype(np.uint32), 'SCALAR', 5125)
            destination['extras']['coverage_guard'] = 'source-piece-retention-v1'
            nf = inv.reshape(-1, 3); _, _, after = coverage_repair(p, t, values['POSITION'], nf)
            if after['restored_pieces']: raise ValueError('written surface still fails coverage')
            row.update(mesh=mi, primitive=pi, source_mesh=sm, source_primitive=sp,
                       input_triangles=len(f), output_triangles=len(nf),
                       retained_candidate_triangles=int(keep.sum()), restored_source_triangles=int(restore.sum()))
            rows.append(row); expected[mi, pi] = (values, inv.ravel())
    if checked != source_pairs: raise ValueError('incomplete source primitive coverage')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as folder:
        stage = Path(folder) / 'coverage'; stage.mkdir()
        payload = compact(changed, blob); target = stage / 'guarded-field.glb'
        write_glb(target, changed, payload); actual, ab = read_glb(target)
        if actual['nodes'] != ld['nodes'] or actual['materials'] != ld['materials']:
            raise ValueError('coverage guard altered hierarchy or appearance')
        for mi, mesh in enumerate(actual['meshes']):
            for pi, prim in enumerate(mesh['primitives']):
                if (mi, pi) in expected: values, indices = expected[mi, pi]
                else:
                    old = ld['meshes'][mi]['primitives'][pi]
                    values = {key: accessor(ld, lb, ai) for key, ai in old['attributes'].items()}
                    indices = accessor(ld, lb, old['indices'])
                if not np.array_equal(accessor(actual, ab, prim['indices']), indices): raise ValueError('written indices differ')
                for key, value in values.items():
                    if not np.array_equal(accessor(actual, ab, prim['attributes'][key]), value): raise ValueError('written attributes differ')
        dump(stage / 'guarded.json', {'schema_version': 1, 'sha256': digest(target),
            'source_sha256': digest(source), 'low_sha256': digest(low),
            'producer_sha256': {p: digest(Path(__file__).parent / p) for p in ['guard_repaired_game.py', 'cad_surface_coverage.py']},
            'placed_triangles': scene_triangles(actual), 'stored_triangles': sum(len(accessor(actual, ab, p['indices'])) // 3 for m in actual['meshes'] for p in m['primitives']),
            'checked_primitives': len(checked), 'checked_source_pieces': checked_pieces,
            'repaired_primitives': rows, 'exported_attributes_verified': True,
            'scope': 'Every primitive and connected source piece checked in local metres, independent of camera. Seven samples per source triangle; 8mm distance and 100 square mm flagged source-area threshold. Not continuous coverage or maximum-error certification. Collision unchanged.'})
        stage.rename(out)
    print(len(rows), 'repaired primitives;', scene_triangles(actual), 'placed triangles')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-game-coverage/guarded')
    guard(parser.parse_args().out)
