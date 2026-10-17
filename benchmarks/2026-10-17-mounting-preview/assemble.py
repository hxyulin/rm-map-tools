#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose full equipment previews using original hierarchy occurrence poses."""
import argparse,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import build_plan,digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out.resolve();report=json.loads((out/'summary.json').read_bytes());original=[r for r in report['components'] if not r['id'].startswith('complete/')];available={r['id']:r for r in original};inventory=json.loads((ROOT/'out/rmuc2027-equipment-pipeline/inventory.json').read_bytes());lookup={r['id']:r for r in inventory['components']};hierarchy_path=ROOT/'out/rmuc2027-hierarchy/hierarchy.json';poses={}
    for n in build_plan(json.loads(hierarchy_path.read_bytes()))['nodes']:
        if n['component_id']:poses.setdefault(n['component_id'],[]).append(n)
    spec=importlib.util.spec_from_file_location('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline);compositions=[]
    for group in ['outpost','rune','technology-core','resource-area','dart-station']:
        members=[cid for cid in lookup if cid.startswith(group+'/') or group=='dart-station' and cid.startswith('dart-station-part-')]
        def data(cid,stage):
            path=out/cid/(stage+'.npz') if cid in available else ROOT/'out/rmuc2027-equipment-pipeline'/cid/'native.npz'
            return np.load(path)
        anchor=max([c for c in members if c.startswith(group+'/')],key=lambda c:len(data(c,'before')['triangles']));ref=data(anchor,'before');center=(ref['positions_mm'].min(0)+ref['positions_mm'].max(0))/2;anchor_matrix=np.array(poses[anchor][0]['world_matrix_mm']);world_center=center@anchor_matrix[:3,:3].T+anchor_matrix[:3,3];placements={}
        for cid in members:
            d=data(cid,'before');local=(d['positions_mm'].min(0)+d['positions_mm'].max(0))/2
            node=min(poses[cid],key=lambda n:np.linalg.norm(local@np.array(n['world_matrix_mm'])[:3,:3].T+np.array(n['world_matrix_mm'])[:3,3]-world_center));placements[cid]=node
        folder=out/'complete'/group;folder.mkdir(parents=True,exist_ok=True);stages={}
        for stage in ['before','holes','fasteners','combined']:
            pp=[];tt=[];mm=[];owners=[];palette=[];offset=0;part_records=[]
            for index,cid in enumerate(members):
                d=data(cid,stage);matrix=np.array(placements[cid]['world_matrix_mm']);p=d['positions_mm']@matrix[:3,:3].T+matrix[:3,3]-world_center;keys=[v or None for v in d['palette'].tolist()];remap=[]
                for key in keys:
                    if key not in palette:palette.append(key)
                    remap.append(palette.index(key))
                pp.append(p);tt.append(d['triangles']+offset);mm.append(np.array(remap)[d['material_ids']]);owners.append(np.full(len(d['triangles']),index));offset+=len(p);part_records.append({'id':cid,'triangles':len(d['triangles']),'source_pose_node_id':placements[cid]['id'],'source_world_matrix_mm':placements[cid]['world_matrix_mm'],'unaffected_original_native_mesh':cid not in available})
            p=np.concatenate(pp);t=np.concatenate(tt);m=np.concatenate(mm);pipeline.save_mesh(folder,stage,p,t,m,palette,np.zeros(len(t),int));np.save(folder/(stage+'-component-indices.npy'),np.concatenate(owners));stages[stage]={'triangles':len(t),'members':part_records,'outputs_sha256':{name:digest(folder/name) for name in [stage+'.glb',stage+'.npz']}}
        row={'id':'complete/'+group,'source_step_sha256':json.loads((ROOT/'out/rmuc2027-mounting-details/audit-final.json').read_bytes())['source_sha256'],'display_rotation':[[1,0,0],[0,0,1],[0,-1,0]],'source_world_origin_mm':world_center.tolist(),'opening_candidates':sum(available[c]['opening_candidates'] for c in members if c in available),'fastener_candidates':sum(available[c]['fastener_candidates'] for c in members if c in available),'withheld_openings':sum(available[c]['withheld_openings'] for c in members if c in available),'stages':stages,'hierarchy_sha256':digest(hierarchy_path),'producer_sha256':digest(Path(__file__)),'scope':'Whole equipment in original occurrence poses; nearest matching occurrence to the anchor equipment chosen for each member. Unaffected source parts retain identical native .4mm/.25rad meshes in every variant. Affected work parts use the isolated .4mm/.6rad previews. No geometry simplification or runtime update in composition.'};(folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n');compositions.append(row);print(group,{s:r['triangles'] for s,r in stages.items()},flush=True)
    report['components']=compositions+original;report['assembly_producer_sha256']=digest(Path(__file__));(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
