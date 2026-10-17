#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Local lower-housing LOD from the approved native detail tessellation."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_local_lod import adaptive_material_lod,guarded_vertex_lod
from plan_cad_lods import digest
from mesh_quality import deviation
from export_field_package import GlbWriter


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--vertex-guards',action='store_true');a=ap.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    policy_path=ROOT/'rules/base-housing-local-lod-rmuc2027.json';policy=json.loads(policy_path.read_bytes());source=ROOT/'out/rmuc2027-base-surface-lods-v3/approved/geometry.npz';reference=ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz';summary=json.loads((ROOT/'out/rmuc2027-base-surface-lods-v3/summary.json').read_bytes());audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes())
    if digest(source)!=summary['stages']['approved']['geometry_sha256']:raise ValueError('approved native detail input mismatch')
    if digest(source)!=policy['native_detail_geometry_sha256'] or digest(reference)!=policy['current_visual_geometry_sha256'] or audit['component_step_sha256']!=policy['component_step_sha256']:raise ValueError('housing policy input mismatch')
    original=np.load(source);base=np.load(reference);index=next(i for i,u in enumerate(audit['units']) if u['source_id']==policy['source_unit_id']);mask=original['unit_ids']==index;tri=original['triangles'][mask];used,inv=np.unique(tri,return_inverse=True);p=original['positions_mm'][used];t=inv.reshape(-1,3);colors=original['triangle_srgb'][mask];palette,m=np.unique(colors,axis=0,return_inverse=True)
    if a.vertex_guards:p1,t1,m1,proof=guarded_vertex_lod(p,t,m,error_mm=policy['error_mm'],sampled_limit_mm=policy['sampled_limit_mm'],sample_count=policy['sample_count'],maximum_iterations=policy['maximum_iterations'])
    else:p1,t1,m1,proof=adaptive_material_lod(p,t,m,error_mm=.25,sampled_limit_mm=1,sample_count=8192,maximum_depth=4,minimum_patch_triangles=512)
    global_check=deviation(p,t,p1,t1,count=16384);old_mask=base['unit_ids']==index;current_check=deviation(base['positions_mm'],base['triangles'][old_mask],p1,t1,count=16384)
    if global_check['max']>policy['sampled_limit_mm']:raise ValueError(f'final native-reference sampled guard failed: {global_check}, triangles={len(t1)}')
    a.out.mkdir(parents=True);np.savez(a.out/'geometry.npz',positions_mm=p1,triangles=t1,triangle_srgb=palette[m1],unit_ids=np.full(len(t1),index,dtype=np.uint32),source_face_ids=np.zeros(len(t1),dtype=np.uint32));writer=GlbWriter('base/housing-local-lod',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; derived local housing LOD candidate'});writer.add_node('source-unit-4527988',p1/1000,t1,[','.join(map(str,c)) for c in palette[m1]],extras={'source_unit_id':4527988,'inspection_only':True});writer.write(a.out/'visual.glb')
    for leaf in proof.get('leaves',proof.get('regions',[])):
        ownership=np.unique(original['source_face_ids'][mask][leaf['input_triangle_indices']]);leaf['source_face_ids']=sorted(map(int,ownership[ownership!=0]));leaf['includes_prior_merged_faces']=bool(np.any(ownership==0))
    report={'component_step_sha256':audit['component_step_sha256'],'policy_sha256':digest(policy_path),'source_geometry_sha256':digest(source),'reference_geometry_sha256':digest(reference),'source_unit_id':4527988,'native_detail_input_triangles':len(t),'previous_housing_triangles':int(old_mask.sum()),'housing_triangles':len(t1),'base_triangles':115648-int(old_mask.sum())+len(t1),'collision_triangles_unchanged':16857,'native_reference_sampled_deviation_mm':global_check,'previous_housing_sampled_deviation_mm':current_check,'lod':proof,'geometry_sha256':digest(a.out/'geometry.npz'),'visual_sha256':digest(a.out/'visual.glb'),'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_local_lod.py',ROOT/'python/simplify_package.py',ROOT/'python/mesh_quality.py']},'scope':'Same 0.25 mm nominal metric and 1 mm sampled guard, applied locally against the approved native detail input. Source CAD, topology features, material values, collision and installed assets are not deliberately edited.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print('housing',int(old_mask.sum()),'->',len(t1),'leaves',len(proof.get('leaves',proof.get('regions',[]))),'sampled',global_check,'previous comparison',current_check,flush=True)
if __name__=='__main__':main()
