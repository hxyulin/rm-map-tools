#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reduce cut-panel seams while preserving the approved non-dark trim."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from scipy.spatial import cKDTree
from cad_local_lod import guarded_vertex_lod
from cad_planar_shell import planar_skin
from plan_cad_lods import digest
from export_field_package import GlbWriter


def main():
    old=np.load(ROOT/'out/rmuc2027-base-top-mounting-row-final/geometry.npz');used=np.unique(old['triangles']);bar=json.loads((ROOT/'out/rmuc2027-base-crossbar-skin/summary.json').read_bytes());corners=old['positions_mm'][used[np.asarray(bar['lod']['protected_source_vertex_indices'])]]
    for face_id in [4202749,4196198]:
        folder=ROOT/'out/rmuc2027-base-panel-trials'/str(face_id);d=np.load(folder/'geometry.npz');mask=np.all(d['triangle_srgb']==[.2]*3,axis=1);used,inv=np.unique(d['triangles'][mask],return_inverse=True);p=d['positions_mm'][used];t=inv.reshape(-1,3);quantized=np.round(p,4);pp,tt,_,skin=planar_skin(quantized,t,np.zeros(len(t),int));tree=cKDTree(pp);distance,nearest=tree.query(corners);locks=set(map(int,nearest[distance<.01]))
        for q in corners[distance>=.01]:locks.update(map(int,np.asarray(tree.query(q,k=min(8,len(pp)))[1]).ravel()))
        p1,t1,_,lod=guarded_vertex_lod(pp,tt,np.zeros(len(tt),int),error_mm=1,sampled_limit_mm=3,sample_count=262144,maximum_iterations=16,protected_vertex_indices=np.array(sorted(locks),dtype=np.int64));trim=d['positions_mm'][d['triangles'][~mask]];p1=np.concatenate([p1,trim.reshape(-1,3)]);t1=np.concatenate([t1,np.arange(len(trim)*3).reshape(-1,3)+len(p1)-len(trim)*3]);c1=np.concatenate([np.tile([.2]*3,(len(t1)-len(trim),1)),d['triangle_srgb'][~mask]]);np.savez(folder/'optimized.npz',positions_mm=p1,triangles=t1,triangle_srgb=c1,unit_ids=np.full(len(t1),d['unit_ids'][0],dtype=np.uint32),source_face_ids=np.zeros(len(t1),dtype=np.uint32));w=GlbWriter('base/panel-trial',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; native panel replacement and local seam LOD'});w.add_node('source-unit-4268930',p1/1000,t1,[','.join(map(str,c)) for c in c1],extras={'source_unit_id':4268930,'inspection_only':True});w.write(folder/'optimized.glb');report={'source_face_id':face_id,'input_sha256':digest(folder/'geometry.npz'),'before_triangles':len(d['triangles']),'after_triangles':len(t1),'position_rounding_step_mm':.0001,'non_dark_trim_geometry_exact':bool(np.array_equal(p1[t1[-len(trim):]],trim)),'skin':skin,'lod':lod,'geometry_sha256':digest(folder/'optimized.npz'),'visual_sha256':digest(folder/'optimized.glb'),'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_panel_replace.py',ROOT/'python/cad_local_lod.py',ROOT/'python/cad_planar_shell.py']}};(folder/'optimization.json').write_text(json.dumps(report,indent=2)+'\n');print(face_id,len(d['triangles']),'->',len(t1),flush=True)
if __name__=='__main__':main()
