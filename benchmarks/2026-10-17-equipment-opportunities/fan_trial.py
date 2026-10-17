#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measure an explicit fan-only exception to frozen unstyled geometry.

Keep source appearance unresolved and preserve the existing neutral fallback;
this trial invents no paint, deletes no CAD face and installs no runtime asset.
"""
import argparse,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from scipy.spatial import cKDTree
from cad_local_lod import guarded_vertex_lod,planar_outline_vertices
from cad_planar_shell import planar_skin
from cad_wall_fill import shape_map
from mesh_quality import deviation
from plan_cad_lods import digest
from validate_parts import read_part
from OCP.TopAbs import TopAbs_SHELL
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);folder=ROOT/'out/rmuc2027-equipment-pipeline/fan/body-2717086';prior=json.loads((folder/'native.json').read_bytes())
    if digest(folder/'source.step')!=prior['source_step_sha256'] or digest(folder/'native.npz')!=prior['native_npz_sha256']:raise ValueError('fan source changed')
    d=np.load(folder/'native.npz');p=d['positions_mm'];t=d['triangles'];m=d['material_ids']
    if d['palette'].tolist()!=['']:raise ValueError('fan source appearance changed')
    doc,reader,error=read_part(str(folder/'source.step'))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));shells=shape_map(root,TopAbs_SHELL)
    if shells.Extent()!=1:raise ValueError('fan ownership changed')
    pp,tt,mm,skin=planar_skin(p,t,m);outline,_=planar_outline_vertices(root,minimum_face_area_mm2=5000,corner_turn_rad=0);distance,nearest=cKDTree(pp).query(outline);locks=set(map(int,nearest[distance<=.01]))
    for point in outline[distance>.01]:locks.update(map(int,np.atleast_1d(cKDTree(pp).query(point,k=min(8,len(pp)))[1])))
    cp,ct,cm,lod=guarded_vertex_lod(pp,tt,mm,error_mm=.25,sampled_limit_mm=1,sample_count=32768,maximum_iterations=12,protected_vertex_indices=np.array(sorted(locks),dtype=np.int64));quality=deviation(p,t,cp,ct,count=32768)
    if quality['max']>1.001:raise ValueError('fan native sampled guard failed')
    spec=importlib.util.spec_from_file_location('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline);pipeline.save_mesh(a.out,'fan-lod-trial',cp,ct,cm,[None],np.ones(len(ct),int))
    report={'id':'fan/body-2717086','source_step_sha256':prior['source_step_sha256'],'native_npz_sha256':prior['native_npz_sha256'],'before_triangles':len(t),'planar_triangles':len(tt),'after_triangles':len(ct),'placed_uses':10,'placed_saving':10*(len(t)-len(ct)),'sampled_native_deviation_mm':quality,'appearance':'Source remains unstyled; existing fallback provenance and material retained. Explicit fan-only diagnostic exception; not a global style-policy change.','lod':lod,'geometry_sha256':digest(a.out/'fan-lod-trial.npz'),'visual_sha256':digest(a.out/'fan-lod-trial.glb'),'producer_sha256':digest(Path(__file__))};(a.out/'fan-trial.json').write_text(json.dumps(report,indent=2)+'\n');print(len(t),'->',len(ct),quality,flush=True)

if __name__=='__main__':main()
