#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explicit micro-hardware omission followed by component-local structural LOD."""
import argparse
import json
from pathlib import Path
from common import ROOT,module,read_mesh,retain_triangles,replace_members
import numpy as np
from cad_component_detail import compact_detail_filter,connected_pieces
from cad_dense_lod import dense_lod,surface_samples
from cad_pass_composition import subset
from plan_cad_lods import digest
from gltf_scene import read_glb,write_glb
from mesh_quality import distances


def port_mask(p,t,paths):
    samples=surface_samples(p,t);keep=np.zeros(len(t),bool)
    for path in paths:
        start,end=np.array([path['start_mm'],path['end_mm']]);delta=end-start;fraction=np.clip(((samples-start)@delta)/(delta@delta),0,1);keep|=np.linalg.norm(samples-start-fraction[:,:,None]*delta,axis=2).min(1)<=20
    return keep


def join(parts):
    pp=[];tt=[];mm=[];offset=0
    for p,t,m in parts:pp.append(p);tt.append(t+offset);mm.append(m);offset+=len(p)
    return np.concatenate(pp),np.concatenate(tt),np.concatenate(mm)


def optical_neighborhood(data,cid,optical):
    """Retain adjacent opaque bezels as well as the light surfaces themselves."""
    p,t,m,u=[data[k]for k in ['positions_mm','triangles','material_ids','unit_ids']];mask=np.isin(m,optical)
    if cid=='dart-station/frame':
        palette=data['palette'];paint=[i for i,c in enumerate(palette)if c and np.max(abs(np.array(list(map(float,c.split(','))))-[.1333,.2902,.7451]))<.00001];mask&=~((u==1)&np.isin(m,paint))
    if not mask.any():return np.zeros(len(t),bool)
    return distances(surface_samples(p,t).reshape(-1,3),p,t[mask]).reshape(-1,7).min(1)<=8


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--occlusion-guards',type=Path);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);prior=ROOT/'out/rmuc2027-dart-outpost/summary.json';ledger=json.loads(prior.read_bytes());checks=json.loads((prior.parent/'validation.json').read_bytes());paths={r['id']:r['qualified_opening_paths']for r in checks['components']};guards={r['id']:r for r in json.loads(a.occlusion_guards.read_bytes())['components']}if a.occlusion_guards else {};rows=[];save=module('writer',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py').save_mesh;count=module('count',ROOT/'benchmarks/2026-10-17-arena-budget/run.py').counts
    if a.occlusion_guards:(out/'applied-optical-guards.json').write_bytes(a.occlusion_guards.read_bytes())
    for row in ledger['components']:
        cid=row['id']
        if not cid.startswith(('dart-station/','outpost/')):continue
        folder=out/cid;folder.mkdir(parents=True,exist_ok=True);source=ROOT/row['visual_glb'];d=read_mesh(source);p,t,m,u=[d[k]for k in ['positions_mm','triangles','material_ids','unit_ids']];palette=d['palette'];optical=[i for i,c in enumerate(palette)if c and np.ptp(list(map(float,c.split(','))))>.1]
        if digest(source)!=row['visual_sha256']:raise ValueError('approved input changed')
        records=[];kept=[];backing_ids=[];light_guard=optical_neighborhood(d,cid,optical);extra_guard=np.zeros(len(t),bool)
        if cid in guards:
            if guards[cid]['source_visual_sha256']!=digest(source):raise ValueError('source occlusion guard changed')
            extra_guard[guards[cid]['protected_input_triangle_indices']]=True;light_guard|=extra_guard
        # These named definitions are the reviewed rigid assembly scopes.
        # Do not share backing with another definition (door, rail or rotor).
        for unit in np.unique(u):
            ids=np.flatnonzero(u==unit);pp,tt,mm=subset(d,u==unit);local_paths=[r for r in paths.get(cid,[])if r['source_member']==unit];ports=port_mask(pp,tt,local_paths)|light_guard[ids];labels=connected_pieces(pp,tt)
            for part in np.unique(labels):
                part_ids=np.flatnonzero(labels==part);span=np.ptp(pp[np.unique(tt[part_ids])],axis=0)
                if span.max()>=17 or np.isin(mm[part_ids],optical).any() or ports[part_ids].any():backing_ids.extend(ids[part_ids])
        backing=(p,t[np.array(backing_ids,dtype=np.int64)])
        for unit in np.unique(u):
            ids=np.flatnonzero(u==unit);pp,tt,mm=subset(d,u==unit);local_paths=[r for r in paths.get(cid,[])if r['source_member']==unit];ports=port_mask(pp,tt,local_paths)|light_guard[ids];selected,proof=compact_detail_filter(pp,tt,mm,protected_material_ids=optical,protected_triangle_indices=np.flatnonzero(ports),rigid_backing_mesh=backing);kept.extend(ids[selected]);records.append({'source_member':int(unit),'detail':proof})
        kept=np.sort(kept);micro=folder/'micro.glb';retain_triangles(source,micro,kept);micro_count=count(micro)['placed_triangles'];data=read_mesh(micro);vp,vt,vm,vu=[data[k]for k in ['positions_mm','triangles','material_ids','unit_ids']];visual=[];contact=[];contact_units=[];lod_records=[]
        light_guard=optical_neighborhood(data,cid,optical)|extra_guard[kept]
        for unit in np.unique(vu):
            unit_ids=np.flatnonzero(vu==unit);pp,tt,mm=subset(data,vu==unit);local_paths=[r for r in paths.get(cid,[])if r['source_member']==unit];ports=port_mask(pp,tt,local_paths);visual_guard=ports|light_guard[unit_ids];labels=connected_pieces(pp,tt);visual_parts=[];contact_parts=[];piece_records=[]
            for part in np.unique(labels):
                ids=np.flatnonzero(labels==part);used,inv=np.unique(tt[ids],return_inverse=True);sp,st,sm=pp[used],inv.reshape(-1,3),mm[ids];port=ports[ids];freeze=visual_guard[ids];record={'piece':int(part),'before':len(st)}
                if len(st)>=96:
                    # Doubled labels protect a local port ring without freezing
                    # the rest of its source material. Restore original labels afterward.
                    tagged=sm+freeze*len(palette);protected=optical+[i+len(palette)for i in range(len(palette))]
                    q,f,k,proof=dense_lod(sp,st,tagged,nominal_error_mm=2,maximum_distance_mm=4,protected_material_ids=protected);k=k%len(palette);record['visual']=proof
                else:q,f,k=sp,st,sm
                visual_parts.append((q,f,k))
                if len(st)>=96:
                    q,f,k,proof=dense_lod(sp,st,port.astype(np.int64),nominal_error_mm=3,maximum_distance_mm=6,protected_material_ids=[1]);record['contact']=proof
                else:q,f,k=sp,st,np.zeros(len(st),int)
                contact_parts.append((q,f,np.zeros(len(f),int)));piece_records.append(record)
            q,f,k=join(visual_parts)
            if len(f)<len(tt):visual.append((q,f,k,int(unit)))
            q,f,k=join(contact_parts);contact.append((q,f,k));contact_units.extend([int(unit)]*len(f));lod_records.append({'source_member':int(unit),'pieces':piece_records})
        target=folder/'visual.glb'
        if visual:replace_members(micro,target,visual,palette,folder)
        else:
            doc,blob=read_glb(micro);write_glb(target,doc,blob)
        q,f,k=join(contact);save(folder,'contact',q,f,k,['0.45,0.65,0.80'],np.array(contact_units));doc,blob=read_glb(folder/'contact.glb')
        for node in doc['nodes']:
            if 'mesh'in node:node['extras'].update(source_native_shell_index=node['extras'].pop('native_shell_index'),derived_geometry=True,collision_only=True,native_identity_claim=False)
        write_glb(folder/'contact.glb',doc,blob)
        record={'id':cid,'uses':row['uses'],'before_visual':len(t),'after_micro':micro_count,'after_visual':count(target)['placed_triangles'],'before_collision':row['collision_budget_per_definition'],'after_collision':len(f),'source_visual_sha256':digest(source),'source_collision_sha256':row['collision_sha256'],'micro_glb_sha256':digest(micro),'visual_glb_sha256':digest(target),'collision_glb_sha256':digest(folder/'contact.glb'),'detail_members':records,'lod_members':lod_records,'producer_sha256':{str(x.relative_to(ROOT)):digest(x)for x in [Path(__file__),Path(__file__).with_name('common.py'),ROOT/'python/cad_component_detail.py',ROOT/'python/cad_dense_lod.py']}}
        (folder/'summary.json').write_text(json.dumps(record,indent=2)+'\n');rows.append(record);print(cid,'visual',len(t),'->',micro_count,'->',record['after_visual'],'collision',row['collision_budget_per_definition'],'->',len(f),flush=True)
    (out/'detail-summary.json').write_text(json.dumps({'components':rows,'prior_ledger_sha256':digest(prior),'port_validation_sha256':digest(prior.parent/'validation.json'),'scope':'Explicit small non-optical component omission near retained larger surfaces, followed by independent piece LOD. No all-view/solid equivalence claim or cross-motion merge; 17 mm size/backing limits, 4 mm visual and 6 mm contact finite guards; exact optical and local port regions.'},indent=2)+'\n')


if __name__=='__main__':main()
