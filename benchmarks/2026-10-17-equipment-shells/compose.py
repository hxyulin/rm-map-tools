#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose the aggressive equipment candidates in the complete source hierarchy."""
import argparse
import copy
import json
from common import ROOT,module
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=__import__('pathlib').Path,required=True);a=ap.parse_args();out=a.out.resolve();prior_path=ROOT/'out/rmuc2027-dart-outpost/summary.json';prior=json.loads(prior_path.read_bytes());details=json.loads((out/'detail-summary.json').read_bytes());edits={r['id']:r for r in details['components']};composition=json.loads((prior_path.parent/'composition.json').read_bytes());count=module('count',ROOT/'benchmarks/2026-10-17-arena-budget/run.py').counts
    for row in composition['components']:
        for key in ['glb','sha256','triangles']:row['reference_'+key]=row['candidate_'+key]
        if row['id']in edits:
            edit=edits[row['id']];folder=out/row['id'];target=folder/'visual.glb'
            if digest(ROOT/row['reference_glb'])!=edit['source_visual_sha256'] or digest(target)!=edit['visual_glb_sha256']:raise ValueError('composition input changed')
            row.update(candidate_glb=str(target.relative_to(ROOT)),candidate_sha256=digest(target),candidate_triangles=edit['after_visual'],policy='compact-hardware-omission-and-piece-lod')
        row['placed_triangles']=row['candidate_triangles']*row['uses']
    composition.update(reference_placed_triangles=prior['totals']['visual_placed'],candidate_placed_triangles=sum(r['placed_triangles']for r in composition['components']),prior_composition_sha256=digest(prior_path.parent/'composition.json'))
    (out/'composition.json').write_text(json.dumps(composition,indent=2)+'\n');hp=ROOT/'out/rmuc2027-hierarchy/hierarchy.json'
    if digest(hp)!=composition['hierarchy_sha256']:raise ValueError('hierarchy changed')
    built=module('assemble',ROOT/'benchmarks/2026-10-17-composed-pipeline/assemble.py').build(out,composition,json.loads(hp.read_bytes()),'candidate');ledger=copy.deepcopy(prior);groups={};components=[]
    for old in prior['components']:
        row=copy.deepcopy(old);cid=row['id']
        if cid in edits:
            e=edits[cid];folder=out/cid;stats=count(folder/'visual.glb');row.update(visual_glb=str((folder/'visual.glb').relative_to(ROOT)),visual_sha256=e['visual_glb_sha256'],visual_per_definition=e['after_visual'],visual_placed=e['after_visual']*row['uses'],stored_triangles=stats['stored_triangles'],referenced_unique_triangles=stats['referenced_unique_triangles'],unreferenced_stored_triangles=stats['stored_triangles']-stats['referenced_unique_triangles'])
            if digest(folder/'contact.glb')!=e['collision_glb_sha256']:raise ValueError('contact input changed')
            if e['after_collision']<old['collision_budget_per_definition']:
                row.update(collision_glb=str((folder/'contact.glb').relative_to(ROOT)),collision_sha256=e['collision_glb_sha256'],collision_budget_per_definition=e['after_collision'],collision_budget_placed=e['after_collision']*row['uses'],collision_method='dedicated candidate')
        if digest(ROOT/row['visual_glb'])!=row['visual_sha256']:raise ValueError('visual checksum mismatch')
        components.append(row);g=groups.setdefault(row['group'],{'group':row['group'],'definitions':0,'uses':0,'visual_placed':0,'stored_triangles':0,'referenced_unique_triangles':0,'unreferenced_stored_triangles':0,'collision_budget_placed':0,'dedicated_collision_definitions':0,'fallback_collision_definitions':0,'visual_only_definitions':0});g['definitions']+=1
        for key in ['uses','visual_placed','stored_triangles','referenced_unique_triangles','unreferenced_stored_triangles','collision_budget_placed']:g[key]+=row[key]
        g[{'dedicated candidate':'dedicated_collision_definitions','visual-derived fallback':'fallback_collision_definitions','visual-only marking':'visual_only_definitions'}[row['collision_method']]]+=1
    ledger.update(components=components,groups=sorted(groups.values(),key=lambda r:-r['visual_placed']),totals={k:sum(r[k]for r in components)for k in prior['totals']},prior_totals=prior['totals'],full_glb=count(out/'candidate-field.glb'),assembly={k:v for k,v in built.items()if k!='definitions'},composition_sha256=digest(out/'composition.json'),producer_sha256=digest(__file__),prior_ledger_sha256=digest(prior_path),detail_summary_sha256=digest(out/'detail-summary.json'),scope='Complete source-pose inspection candidate with explicit micro-hardware omission and per-piece LOD in ten rigid Dart/Outpost definitions. Rigid hierarchy and independent door/rotor scopes retained. Contacts are prospective, not runtime bindings.')
    ledger.pop('proofs',None)
    if ledger['totals']['visual_placed']!=ledger['full_glb']['placed_triangles']or ledger['totals']['stored_triangles']!=ledger['full_glb']['stored_triangles']:raise ValueError('full arena accounting differs')
    (out/'summary.json').write_text(json.dumps(ledger,indent=2)+'\n');print(json.dumps({'totals':ledger['totals'],'groups':ledger['groups'],'full_glb':ledger['full_glb']},indent=2))


if __name__=='__main__':main()
