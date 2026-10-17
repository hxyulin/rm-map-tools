#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Try planar reconstruction and source-referenced LOD on five residual work parts."""
import argparse, json, math, sys
from pathlib import Path
from audit import ROOT,TARGETS,module
import numpy as np
from cad_pass_composition import subset
from cad_planar_shell import planar_skin
from cad_structural_skin import structural_skin
from cad_local_lod import planar_outline_vertices
from plan_cad_lods import digest
from mesh_quality import deviation

POLICIES={
 'rune/banks/bank-a/hub-cluster':[18,19],
 'rune/banks/bank-b/hub-cluster':[18,19],
 'rune/support-and-shared':[15,20,21,37,45,46,62,78],
 'resource-area/mechanism':[4,29,30,31,32,33,34,72],
 'technology-core/tool-head':[4,33,1195,1197,1211,1224,1428],
}

def join(parts):
    pp=[];tt=[];mm=[];uu=[];offset=0
    for p,t,m,unit in parts:pp.append(p);tt.append(t+offset);mm.append(m);uu.append(np.full(len(t),unit,int));offset+=len(p)
    return tuple(np.concatenate(v) for v in [pp,tt,mm,uu])


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    audit=json.loads((a.out/'audit.json').read_bytes());lookup={c['id']:c for c in audit['components']};composition=module('composition',ROOT/'benchmarks/2026-10-17-composed-pipeline/run.py');pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');results=[]
    producers={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_structural_skin.py',ROOT/'python/cad_planar_shell.py',ROOT/'python/cad_local_lod.py']}
    for cid in TARGETS:
        folder=a.out/cid;folder.mkdir(parents=True,exist_ok=True);prior=lookup[cid];reference=ROOT/'out/rmuc2027-composed-pipeline'/cid/'candidate.npz'
        if digest(reference)!=prior['reference_npz_sha256']:raise ValueError('reference changed')
        record_path=folder/'summary.json'
        if record_path.exists():
            cached=json.loads(record_path.read_bytes())
            if cached['producer_sha256']!=producers or cached['reference_npz_sha256']!=digest(reference):raise ValueError('stale reduction cache')
            for name,sha in cached['outputs_sha256'].items():
                if digest(folder/name)!=sha:raise ValueError('cached reduction changed')
            results.append(cached);print('cached',cid,flush=True);continue
        base=dict(np.load(reference));palette=[c or None for c in base['palette'].tolist()];source=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step';doc,reader,faces,shells,owner=composition.native(source)
        native_dir=ROOT/'out/rmuc2027-mounting-native'/cid;source_mesh=dict(np.load(native_dir/'combined.npz'));face_ids=np.load(native_dir/'combined-native-face-indices.npy');source_mesh['unit_ids']=np.array([owner[abs(int(i))] for i in face_ids]);source_mesh['material_ids']=np.array([palette.index(c or None) for c in source_mesh['palette'].tolist()])[source_mesh['material_ids']]
        stages={'planar':[],'detail':[]};records=[]
        for unit in np.unique(base['unit_ids']):
            p,t,m=subset(base,base['unit_ids']==unit);record={'unit':int(unit),'before':len(t)}
            if len(t)>=32 and int(unit) in POLICIES[cid]:
                q,f,k,proof=planar_skin(p,t,m)
                quality=deviation(p,t,q,f,count=8192)
                if quality['max']>.004:raise ValueError('planar skin exceeded numerical budget')
            else:q,f,k=p,t,m;proof={'patches':[]};quality=None
            stages['planar'].append((q,f,k,int(unit)));record['planar']=len(f);record['planar_sampled_deviation_mm']=quality
            candidate=(q,f,k,int(unit));record['selected_for_source_detail']=int(unit) in POLICIES[cid]
            if record['selected_for_source_detail']:
                original=source_mesh['unit_ids']==unit
                if not original.any():raise ValueError('selected shell missing from edited source')
                sp,st,sm=subset(source_mesh,original)
                # Only these explicit structural shells relax the broad unknown/color geometry freeze.
                # The logo/light shell 17 and Tech Core green/red target units remain unselected.
                outline,outline_proof=planar_outline_vertices(shells.FindKey(int(unit)),minimum_face_area_mm2=5000,corner_turn_rad=math.radians(15))
                limit=1 if max(np.ptp(sp,axis=0))<150 else 3
                nominal=.5 if limit==1 else 1
                qp,qt,qm,guard=structural_skin(sp,st,sm,outline_points_mm=outline,nominal_error_mm=nominal,sampled_limit_mm=limit)
                record['source_detail']=guard
                if len(qt)<len(f):candidate=(qp,qt,qm,int(unit));record['adopted_source_detail']=True
                else:record['adopted_source_detail']=False
            stages['detail'].append(candidate);record['detail']=len(candidate[1]);records.append(record)
        for stage,parts in stages.items():
            p,t,m,u=join(parts);pipeline.save_mesh(folder,stage,p,t,m,palette,u)
        result={'id':cid,'uses':prior['uses'],'source_step_sha256':prior['source_step_sha256'],'reference_npz_sha256':digest(reference),'reference_glb_sha256':prior['reference_glb_sha256'],'native_edited_npz_sha256':digest(native_dir/'combined.npz'),'native_edited_face_ledger_sha256':digest(native_dir/'combined-native-face-indices.npy'),'before':len(base['triangles']),'planar':sum(len(v[1]) for v in stages['planar']),'detail':sum(len(v[1]) for v in stages['detail']),'units':records,'producer_sha256':producers,'outputs_sha256':{name:digest(folder/name) for name in ['planar.glb','planar.npz','detail.glb','detail.npz']}}
        record_path.write_text(json.dumps(result,indent=2)+'\n');results.append(result);print(cid,result['before'],'-> planar',result['planar'],'-> detail',result['detail'],flush=True)
    report={'components':results,'audit_sha256':digest(a.out/'audit.json'),'producer_sha256':producers,'reference_field_placed_triangles':1573606,'placed_saving':sum((r['before']-r['detail'])*r['uses'] for r in results),'scope':'Source-owned per-shell planar boundary reconstruction, then explicit structural LOD from original edited native inputs. No additional holes, fasteners or native components deliberately removed. Optical/artwork owners are not selected for detail LOD. Unselected shells retain the planar or exact original geometry. No runtime/collision change.'};report['candidate_field_placed_triangles']=1573606-report['placed_saving'];(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PLACED SAVING',report['placed_saving'],'FIELD',report['candidate_field_placed_triangles'],flush=True)
if __name__=='__main__':main()
