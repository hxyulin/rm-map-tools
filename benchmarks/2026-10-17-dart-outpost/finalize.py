#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Choose contact candidates per member, validate actual exports and compose arena."""
import argparse
import copy
import json
from pathlib import Path
from run import ROOT,module,join,save_mesh,counts
import numpy as np
from gltf_scene import read_glb,write_glb,accessor,mesh_instances
from mesh_quality import distances
from plan_cad_lods import digest


def optical_geometry(path, protected):
    d,b=read_glb(path);result={}
    for node,pi,p,t,mi in mesh_instances(d,b):
        color=d['materials'][mi]['extras']['step_colour_srgb']
        if tuple(color or []) not in protected:continue
        result.setdefault(tuple(color),[]).extend(map(tuple,p[t].reshape(-1,9)))
    return {str(k):sorted(v) for k,v in result.items()}


def exact_untouched(source,target,selected):
    sd,sb=read_glb(source);td,tb=read_glb(target);now={n['extras']['native_shell_index']:n for n in td['nodes'] if 'mesh'in n and 'native_shell_index'in n.get('extras',{})};exact=0
    for old in sd['nodes']:
        if 'mesh' not in old:continue
        unit=old['extras']['native_shell_index']
        if unit in selected:continue
        current=now[unit];a=sd['meshes'][old['mesh']]['primitives'];b=td['meshes'][current['mesh']]['primitives']
        if len(a)!=len(b):raise ValueError('untouched primitive count changed')
        for first,second in zip(a,b):
            if sd['materials'][first['material']]!=td['materials'][second['material']]:raise ValueError('untouched material changed')
            for key,index in first['attributes'].items():
                if not np.array_equal(accessor(sd,sb,index),accessor(td,tb,second['attributes'][key])):raise ValueError('untouched attribute changed')
            if not np.array_equal(accessor(sd,sb,first['indices']),accessor(td,tb,second['indices'])):raise ValueError('untouched index changed')
            exact+=sd['accessors'][first['indices']]['count']//3
    return exact


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();detail=json.loads((out/'detail-summary.json').read_bytes());prior=json.loads((ROOT/'out/rmuc2027-arena-budget/summary.json').read_bytes());by={r['id']:r for r in prior['components']};overrides={};proofs=[]
    for r in detail['components']:
        cid=r['id'];old=by[cid];folder=out/cid
        for name,sha in r['outputs_sha256'].items():
            if digest(folder/name)!=sha:raise ValueError('candidate changed')
        source=ROOT/old['visual_glb'];target=folder/'visual.glb';d,b=read_glb(target);selected={n['extras']['source_native_shell_index'] for n in d['nodes'] if 'mesh'in n and n.get('extras',{}).get('derived_geometry')}
        exact=exact_untouched(source,target,selected)
        sd,sb=read_glb(source);protected={tuple(mat['extras']['step_colour_srgb']) for mat in sd['materials'] if mat['extras']['step_colour_srgb'] and np.ptp(mat['extras']['step_colour_srgb'])>.1}
        if sd['materials']!=d['materials']:raise ValueError('source PBR material table changed')
        if optical_geometry(source,protected)!=optical_geometry(target,protected):raise ValueError('exported optical triangles changed')
        # A definition-wide choice misses wins on small hardware when earlier
        # panel prisms are cheaper on broad members. Compare inside each owner.
        previous_path=(ROOT/old['collision_glb']).with_suffix('.npz');before=np.load(previous_path);new=np.load(folder/'contact.npz');chunks=[];members=[]
        if set(before['unit_ids'])!=set(new['unit_ids']):raise ValueError('collision owner set changed')
        for unit in np.unique(new['unit_ids']):
            old_mask=before['unit_ids']==unit;new_mask=new['unit_ids']==unit;adopt=int(new_mask.sum())<int(old_mask.sum());data=new if adopt else before;mask=new_mask if adopt else old_mask
            used,inv=np.unique(data['triangles'][mask],return_inverse=True);p,t=data['positions_mm'][used],inv.reshape(-1,3);chunks.append((p,t,np.zeros(len(t),int),int(unit)));members.append({'source_member':int(unit),'previous_triangles':int(old_mask.sum()),'new_triangles':int(new_mask.sum()),'chosen': 'dense-6mm' if adopt else old['collision_method'],'output_triangles':len(t)})
        p,t,m,u=join(chunks);save_mesh(folder,'contact-composed',p,t,m,['0.45,0.65,0.80'],u);cd,cb=read_glb(folder/'contact-composed.glb')
        for node in cd['nodes']:
            if 'mesh'in node:node['extras'].update(collision_only=True,derived_geometry=True,native_identity_claim=False,source_native_shell_index=node['extras'].pop('native_shell_index'))
        write_glb(folder/'contact-composed.glb',cd,cb)
        approved=np.load(source.with_suffix('.npz'));checks=[]
        for unit in np.unique(u):
            original=approved['triangles'][approved['unit_ids']==unit];faces=t[u==unit];actual=np.concatenate([q[f].reshape(-1,3)*1000 for node,_,q,f,_ in mesh_instances(cd,cb) if cd['nodes'][node]['extras']['source_native_shell_index']==unit])
            from scipy.spatial import cKDTree
            quantization=float(cKDTree(p[np.unique(faces)]).query(actual)[0].max())
            worst=float(max(distances(approved['positions_mm'][np.unique(original)],p,faces).max(),distances(actual,approved['positions_mm'],original).max()))
            if quantization>.002 or worst>6.005:raise ValueError('actual exported contact vertex guard failed '+cid+' '+str(unit)+' '+str(worst))
            checks.append({'source_member':int(unit),'maximum_exported_vertex_distance_mm':worst,'maximum_export_quantization_mm':quantization})
        overrides[cid]={'visual_glb':str(target.relative_to(ROOT)),'visual_sha256':digest(target),'visual_triangles':r['visual'],'collision_glb':str((folder/'contact-composed.glb').relative_to(ROOT)),'collision_sha256':digest(folder/'contact-composed.glb'),'collision_triangles':len(t)}
        proofs.append({'id':cid,'exact_untouched_visual_triangles':exact,'optical_positions_and_pbr_exact':True,'collision_members':members,'collision_vertex_checks':checks,'previous_collision_npz_sha256':digest(previous_path)})
        print(cid,'visual',r['before'],'->',r['visual'],'collision',r['previous_collision'],'->',len(t),flush=True)
    oldcomp=ROOT/'out/rmuc2027-arena-budget/composition.json';composition=json.loads(oldcomp.read_bytes());rows=[]
    for old in composition['components']:
        r=copy.deepcopy(old)
        for key in ['glb','sha256','triangles']:r['reference_'+key]=old['candidate_'+key]
        if r['id'] in overrides:
            v=overrides[r['id']];r.update(candidate_glb=v['visual_glb'],candidate_sha256=v['visual_sha256'],candidate_triangles=v['visual_triangles'],policy='dense-material-local-2mm')
        r['placed_triangles']=r['candidate_triangles']*r['uses'];rows.append(r)
    composition.update(components=rows,reference_placed_triangles=sum(r['reference_triangles']*r['uses'] for r in rows),candidate_placed_triangles=sum(r['placed_triangles'] for r in rows),prior_composition_sha256=digest(oldcomp));(out/'composition.json').write_text(json.dumps(composition,indent=2)+'\n')
    hp=ROOT/'out/rmuc2027-hierarchy/hierarchy.json'
    if digest(hp)!=composition['hierarchy_sha256']:raise ValueError('hierarchy changed')
    built=module('assemble',ROOT/'benchmarks/2026-10-17-composed-pipeline/assemble.py').build(out,composition,json.loads(hp.read_bytes()),'candidate')
    ledger=copy.deepcopy(prior);groups={r['group']:{**r,'visual_placed':0,'stored_triangles':0,'referenced_unique_triangles':0,'collision_budget_placed':0,'dedicated_collision_definitions':0,'fallback_collision_definitions':0,'visual_only_definitions':0} for r in prior['groups']}
    for row in ledger['components']:
        if row['id']in overrides:
            v=overrides[row['id']];row.update(visual_glb=v['visual_glb'],visual_sha256=v['visual_sha256'],visual_per_definition=v['visual_triangles'],visual_placed=v['visual_triangles']*row['uses'],collision_glb=v['collision_glb'],collision_sha256=v['collision_sha256'],collision_budget_per_definition=v['collision_triangles'],collision_budget_placed=v['collision_triangles']*row['uses'],collision_method='dedicated candidate');stats=counts(ROOT/row['visual_glb']);row['stored_triangles']=stats['stored_triangles'];row['referenced_unique_triangles']=stats['referenced_unique_triangles']
        g=groups[row['group']]
        for k in ['visual_placed','stored_triangles','referenced_unique_triangles','collision_budget_placed']:g[k]+=row[k]
        g[{'dedicated candidate':'dedicated_collision_definitions','visual-derived fallback':'fallback_collision_definitions','visual-only marking':'visual_only_definitions'}[row['collision_method']]]+=1
    ledger['groups']=sorted(groups.values(),key=lambda r:-r['visual_placed']);ledger['totals']={k:sum(r[k] for r in ledger['components']) for k in prior['totals']};ledger['full_glb']=counts(out/'candidate-field.glb');ledger['assembly']={k:v for k,v in built.items() if k!='definitions'};ledger['prior_totals']=prior['totals'];ledger['proofs']=proofs;ledger['producer_sha256']=digest(__file__);ledger['detail_summary_sha256']=digest(out/'detail-summary.json');ledger['composition_sha256']=digest(out/'composition.json');ledger['scope']='Complete arena with nine Dart/Outpost definition overrides. Exact optical triangle positions/PBR and untouched member attributes. Separate prospective contact budget; no runtime, motion binding or detector change.'
    if ledger['full_glb']['placed_triangles']!=ledger['totals']['visual_placed'] or ledger['full_glb']['stored_triangles']!=ledger['totals']['stored_triangles']:raise ValueError('field accounting mismatch')
    # Do not carry the preceding phase's producer-specific interior payload.
    ledger.pop('interior',None);(out/'summary.json').write_text(json.dumps(ledger,indent=2)+'\n');print(json.dumps({'totals':ledger['totals'],'groups':ledger['groups']},indent=2))


if __name__=='__main__':main()
