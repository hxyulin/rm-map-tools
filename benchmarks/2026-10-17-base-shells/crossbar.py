#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Rebuild crossbar tessellation with native corner guards and planar skins."""
import argparse,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from scipy.spatial import cKDTree
from cad_local_lod import planar_outline_vertices,guarded_vertex_lod
from cad_planar_shell import planar_skin
from cad_wall_fill import shape_map
from validate_parts import read_part
from plan_cad_lods import digest
from export_field_package import GlbWriter
from mesh_quality import deviation
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();source=ROOT/'out/rmuc2027-base-structure-audit/source.step';reference=ROOT/'out/rmuc2027-base-top-mounting-row-final/geometry.npz';baseline=json.loads((reference.parent/'summary.json').read_bytes());audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());d=np.load(reference);used,inv=np.unique(d['triangles'],return_inverse=True);p=d['positions_mm'][used];t=inv.reshape(-1,3);palette,m=np.unique(d['triangle_srgb'],axis=0,return_inverse=True)
    if digest(source)!=audit['component_step_sha256'] or digest(reference)!=baseline['geometry_sha256']:raise ValueError('approved source mismatch')
    doc,reader,error=read_part(str(source))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);solids=shape_map(root,TopAbs_SOLID);index=next(i for i,u in enumerate(audit['units']) if u['source_id']==4268930);indices={f['native_face_index'] for f in audit['faces'] if f['unit']==index}
    for j in range(1,solids.Extent()+1):
        shape=solids.FindKey(j);ff=shape_map(shape,TopAbs_FACE)
        if {faces.FindIndex(ff.FindKey(k)) for k in range(1,ff.Extent()+1)}==indices:break
    else:raise ValueError('source crossbar missing')
    outline,selection=planar_outline_vertices(shape,minimum_face_area_mm2=20000,corner_turn_rad=math.radians(15));dist,near=cKDTree(p).query(outline);locks=set(map(int,near[dist<=.01]));missing=np.flatnonzero(dist>.01)
    for k in missing:locks.update(map(int,np.asarray(cKDTree(p).query(outline[k],k=min(8,len(p)))[1]).ravel()))
    pp,tt,mm,proof=guarded_vertex_lod(p,t,m,error_mm=1,sampled_limit_mm=3,sample_count=262144,maximum_iterations=16,protected_vertex_indices=np.asarray(sorted(locks),dtype=np.int64));quality=deviation(p,t,pp,tt,count=16384);before_skin=len(tt);pp,tt,mm,skin=planar_skin(pp,tt,mm);final_quality=deviation(p,t,pp,tt,count=16384)
    if final_quality['max']>3:raise ValueError('combined sampled guard failed')
    a.out.mkdir(parents=True,exist_ok=True);np.savez(a.out/'geometry.npz',positions_mm=pp,triangles=tt,triangle_srgb=palette[mm],unit_ids=np.full(len(tt),index,dtype=np.uint32),source_face_ids=np.zeros(len(tt),dtype=np.uint32));w=GlbWriter('base/crossbar-skin',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; outline-guarded crossbar and planar skins'});w.add_node('source-unit-4268930',pp/1000,tt,[','.join(map(str,c)) for c in palette[mm]],extras={'source_unit_id':4268930,'inspection_only':True});w.write(a.out/'visual.glb');report={'source_unit_id':4268930,'source_step_sha256':digest(source),'approved_geometry_sha256':digest(reference),'before_triangles':len(t),'guarded_triangles':before_skin,'after_triangles':len(tt),'outline_selection':selection,'direct_native_matches':int((dist<=.01).sum()),'native_corner_fallbacks':int(len(missing)),'native_corner_fallback_distance_mm':dist[missing].tolist(),'lod':proof,'guarded_deviation_mm':quality,'skin':skin,'final_sampled_deviation_mm':final_quality,'visual_sha256':digest(a.out/'visual.glb'),'geometry_sha256':digest(a.out/'geometry.npz'),'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_local_lod.py',ROOT/'python/cad_planar_shell.py',ROOT/'python/simplify_package.py']},'scope':'Approximate 1 mm nominal / 3 mm sampled crossbar LOD against the approved hole-closed crossbar. Retains derived closures; not a new source B-rep shell or a proof of native-trim distance.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(len(t),'->',before_skin,'->',len(tt),final_quality,flush=True)
if __name__=='__main__':main()
