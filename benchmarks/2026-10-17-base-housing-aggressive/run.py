#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Aggressive source-outline-protected housing detail LOD, isolated for review."""
import argparse,json,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from scipy.spatial import cKDTree
from cad_local_lod import planar_outline_vertices,guarded_vertex_lod
from cad_wall_fill import shape_map
from validate_parts import read_part
from plan_cad_lods import digest
from export_field_package import GlbWriter
from mesh_quality import deviation
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--sparse-outline-locks',action='store_true');a=ap.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    source=ROOT/'out/rmuc2027-base-structure-audit/source.step';audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());reference=ROOT/'out/rmuc2027-base-surface-lods-v3/approved/geometry.npz';prior=ROOT/'out/rmuc2027-base-housing-local-final';approved=json.loads((prior/'summary.json').read_bytes())
    if digest(source)!=audit['component_step_sha256'] or digest(reference)!=approved['source_geometry_sha256'] or digest(prior/'geometry.npz')!=approved['geometry_sha256']:raise ValueError('source or approved candidate changed')
    d=np.load(reference);index=next(i for i,u in enumerate(audit['units']) if u['source_id']==4527988);mask=d['unit_ids']==index;used,inv=np.unique(d['triangles'][mask],return_inverse=True);p=d['positions_mm'][used];t=inv.reshape(-1,3);palette,m=np.unique(d['triangle_srgb'][mask],axis=0,return_inverse=True);doc,reader,error=read_part(str(source))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);solids=shape_map(root,TopAbs_SOLID);indices={f['native_face_index'] for f in audit['faces'] if f['unit']==index}
    for j in range(1,solids.Extent()+1):
        shape=solids.FindKey(j);local=shape_map(shape,TopAbs_FACE)
        if {faces.FindIndex(local.FindKey(k)) for k in range(1,local.Extent()+1)}==indices:break
    else:raise ValueError('housing source missing')
    outline,selection=planar_outline_vertices(shape,minimum_face_area_mm2=20000 if a.sparse_outline_locks else 5000,corner_turn_rad=math.radians(15) if a.sparse_outline_locks else 0);dist,nearest=cKDTree(p).query(outline);protected=set(map(int,nearest[dist<=.01]));missing=np.flatnonzero(dist>.01)
    for k in missing:protected.update(map(int,cKDTree(p).query(outline[k],k=min(8,len(p)))[1]))
    for record in selection['wires']:record['source_face_id']=next(f['source_face_id'] for f in audit['faces'] if f['native_face_index']==faces.FindIndex(local.FindKey(record['native_face_index'])))
    p1,t1,m1,proof=guarded_vertex_lod(p,t,m,error_mm=1,sampled_limit_mm=3,sample_count=65536,maximum_iterations=16,protected_vertex_indices=np.asarray(sorted(protected),dtype=np.int64));quality=deviation(p,t,p1,t1,count=16384)
    if quality['max']>3:raise ValueError('aggressive guard failed')
    a.out.mkdir(parents=True);np.savez(a.out/'geometry.npz',positions_mm=p1,triangles=t1,triangle_srgb=palette[m1],unit_ids=np.full(len(t1),index,dtype=np.uint32),source_face_ids=np.zeros(len(t1),dtype=np.uint32));w=GlbWriter('base/housing-aggressive',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; derived outline-protected aggressive detail LOD'});w.add_node('source-unit-4527988',p1/1000,t1,[','.join(map(str,c)) for c in palette[m1]],extras={'source_unit_id':4527988,'inspection_only':True});w.write(a.out/'visual.glb')
    selection['sample_points_mm']=outline.tolist();selection['reference_vertex_distances_mm']=dist.tolist();selection['direct_matches']=int((dist<=.01).sum());selection['neighbor_fallback_points']=len(missing)
    report={'component_step_sha256':digest(source),'source_geometry_sha256':digest(reference),'reference_geometry_sha256':digest(ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz'),'approved_housing_geometry_sha256':digest(prior/'geometry.npz'),'previous_housing_triangles':approved['housing_triangles'],'housing_triangles':len(t1),'base_triangles':approved['base_triangles']-approved['housing_triangles']+len(t1),'collision_triangles_unchanged':16857,'material_palette_srgb':palette.tolist(),'outline_selection':selection,'lod':proof,'native_reference_sampled_deviation_mm':quality,'geometry_sha256':digest(a.out/'geometry.npz'),'visual_sha256':digest(a.out/'visual.glb'),'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_local_lod.py',ROOT/'python/simplify_package.py']},'scope':'Explicit 1 mm nominal / 3 mm sampled detail budget with source-native outline corner locks. Source B-rep, installed assets, collision, detectors and previous approved candidate remain unchanged.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print('housing',approved['housing_triangles'],'->',len(t1),'protected',len(protected),'direct outline matches',selection['direct_matches'],'fallbacks',len(missing),'sampled',quality,flush=True)
if __name__=='__main__':main()
