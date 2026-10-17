#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Trial Base-quality detail LOD on two pinned equipment structural shells.

Source geometry/appearance belongs to DJI / RoboMaster. No collision or runtime
replacement; only source shell 1 in the two explicit work parts is eligible.
"""
import argparse,importlib.util,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from scipy.spatial import cKDTree
from cad_local_lod import guarded_vertex_lod,planar_outline_vertices
from cad_planar_shell import planar_skin
from cad_wall_fill import shape_map
from mesh_quality import deviation,distances
from plan_cad_lods import digest
from validate_parts import read_part
from OCP.TopAbs import TopAbs_SHELL
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--id',choices=['dart-station/frame','outpost/fixed/upper-cluster']);ap.add_argument('--colour-margin-mm',type=float,default=0);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    if not math.isfinite(a.colour_margin_mm) or a.colour_margin_mm<0:raise ValueError('invalid colour margin')
    spec=importlib.util.spec_from_file_location('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
    source=ROOT/'out/rmuc2027-equipment-pipeline';ledger=json.loads((source/'passes.json').read_bytes());results=[]
    for cid in ['dart-station/frame','outpost/fixed/upper-cluster']:
        if a.id and cid!=a.id:continue
        prior=next(r for r in ledger['components'] if r['id']==cid);folder=source/cid;target=a.out/cid;target.mkdir(parents=True,exist_ok=True)
        if digest(folder/'native.npz')!=prior['native_npz_sha256'] or digest(folder/'source.step')!=prior['source_step_sha256'] or digest(folder/'lod.glb')!=prior['outputs_sha256']['lod.glb']:raise ValueError('pinned source/reference changed')
        native=np.load(folder/'native.npz');approved=np.load(folder/'lod.npz');palette=[v or None for v in native['palette'].tolist()];protected=[i for i,c in enumerate(palette) if c is None or np.ptp(list(map(float,c.split(','))))>.1];ids=native['unit_ids']==1;used,inv=np.unique(native['triangles'][ids],return_inverse=True);p=native['positions_mm'][used];t=inv.reshape(-1,3);m=native['material_ids'][ids]
        doc,reader,error=read_part(str(folder/'source.step'))
        if error:raise ValueError(error)
        labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels);root=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));shell=shape_map(root,TopAbs_SHELL).FindKey(1)
        p1,t1,m1,skin=planar_skin(p,t,m,protected_material_ids=protected);outline,outline_proof=planar_outline_vertices(shell,minimum_face_area_mm2=20000,corner_turn_rad=math.radians(15));tree=cKDTree(p1);distance,nearest=tree.query(outline);locks=set(map(int,nearest[distance<=.01]));missing=outline[distance>.01]
        for point in missing:locks.update(map(int,np.atleast_1d(tree.query(point,k=min(8,len(p1)))[1])))
        locks.update(np.unique(t1[np.isin(m1,protected)]).tolist());halo=[]
        if a.colour_margin_mm:
            chromatic=[i for i,c in enumerate(palette) if c is not None and np.ptp(list(map(float,c.split(','))))>.1];colour_faces=t1[np.isin(m1,chromatic)]
            if len(colour_faces):halo=np.flatnonzero(distances(p1,p1,colour_faces)<=a.colour_margin_mm);locks.update(map(int,halo))
        attempts=[]
        for metric in [1,.5,.25]:
            pp,tt,mm,proof=guarded_vertex_lod(p1,t1,m1,error_mm=metric,sampled_limit_mm=3,sample_count=32768,maximum_iterations=12,protected_vertex_indices=np.array(sorted(locks),dtype=np.int64))
            keep=~np.isin(mm,protected);original=np.isin(m,protected);tt=np.concatenate([tt[keep],t[original]+len(pp)]);mm=np.r_[mm[keep],m[original]];pp=np.concatenate([pp,p]);quality=deviation(p,t,pp,tt,count=32768)
            attempts.append({'nominal_error_mm':metric,'triangles':len(tt),'sampled_deviation_mm':quality,'accepted':quality['max']<=3.001,'guard':proof})
            if quality['max']<=3.001:break
        else:raise ValueError('no qualifying structural LOD')
        for key in protected:
            if sorted(map(tuple,p[t[m==key]].reshape(-1,9)))!=sorted(map(tuple,pp[tt[mm==key]].reshape(-1,9))):raise ValueError('protected source material changed')
        keep=approved['unit_ids']!=1;offset=len(approved['positions_mm']);full_p=np.concatenate([approved['positions_mm'],pp]);full_t=np.concatenate([approved['triangles'][keep],tt+offset]);full_m=np.r_[approved['material_ids'][keep],mm];full_u=np.r_[approved['unit_ids'][keep],np.ones(len(tt),int)]
        pipeline.save_mesh(target,'candidate',full_p,full_t,full_m,palette,full_u)
        # Freeze a local-space unit export for isolated inspection.
        pipeline.save_mesh(target,'shell',pp,tt,mm,palette,np.ones(len(tt),int))
        result={'id':cid,'changed_native_shell':1,'source_step_sha256':prior['source_step_sha256'],'native_npz_sha256':prior['native_npz_sha256'],'approved_npz_sha256':digest(folder/'lod.npz'),'approved_glb_sha256':digest(folder/'lod.glb'),'native_triangles':len(native['triangles']),'approved_triangles':len(approved['triangles']),'candidate_triangles':len(full_t),'approved_main_shell_triangles':int((approved['unit_ids']==1).sum()),'candidate_main_shell_triangles':len(tt),'protected_material_ids':protected,'colour_margin_mm':a.colour_margin_mm,'colour_margin_locked_vertices':len(halo),'native_outline_selection':outline_proof,'native_outline_points':len(outline),'outline_neighbor_fallbacks':len(missing),'planar_triangles':len(t1),'attempts':attempts,'sampled_deviation_mm':quality,'outputs_sha256':{name:digest(target/name) for name in ['candidate.glb','candidate.npz','shell.glb','shell.npz']}}
        (target/'summary.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result);print(cid,len(approved['triangles']),'->',len(full_t),quality,flush=True)
    report={'components':results,'source_ledger_sha256':digest(source/'passes.json'),'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_local_lod.py',ROOT/'python/cad_planar_shell.py',ROOT/'python/simplify_package.py']},'scope':'Only two explicit native shell identities; original native .4/.25 mesh is the error reference, not cumulative LOD. 1 mm nominal / 3 mm sampled Base-quality detail policy; exact chromatic/unresolved triangles and all other shells retained. No hole fill, component removal, collision or runtime change.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
