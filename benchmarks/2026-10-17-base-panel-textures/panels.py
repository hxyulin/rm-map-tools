#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Qualify selected native crossbar panel prisms and replace their internal detail."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_panel_replace import clip_panel_mesh
from cad_surface_lods import profile_prism,material_lod
from cad_detail_passes import mesh_native_detail
from cad_wall_fill import shape_map
from validate_parts import read_part
from plan_cad_lods import digest
from export_field_package import GlbWriter
from mesh_quality import deviation
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);source=ROOT/'out/rmuc2027-base-structure-audit/source.step';reference=ROOT/'out/rmuc2027-base-crossbar-skin/geometry.npz';audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());byid={f['source_face_id']:f for f in audit['faces']};d=np.load(reference);
    if digest(reference)!=json.loads((reference.parent/'summary.json').read_bytes())['geometry_sha256']:raise ValueError('approved crossbar changed')
    p=d['positions_mm'];t=d['triangles'];c=d['triangle_srgb'];doc,reader,error=read_part(str(source))
    if digest(source)!=audit['component_step_sha256']:raise ValueError('native source changed')
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);faces=shape_map(XCAFDoc_ShapeTool.GetShape_s(roots.Value(1)),TopAbs_FACE);report={'source_sha256':digest(source),'reference_sha256':digest(reference),'stages':[]}
    for face_id,depth in [(4202749,-6),(4196198,8),(4213567,-3),(4222186,-3)]:
        face=faces.FindKey(byid[face_id]['native_face_index']);solid,profile=profile_prism(face,depth_mm=depth,maximum_gap_mm=17);pp,tt,cc,proof=clip_panel_mesh(p,t,c,solid);skin_p,skin_t,_,_,native=mesh_native_detail(solid,['.2,.2,.2']*shape_map(solid,TopAbs_FACE).Extent());skin_p,skin_t,_,lod=material_lod(skin_p,skin_t,np.zeros(len(skin_t),int),error_mm=.25,sampled_limit_mm=1,sample_count=16384);p1=np.concatenate([pp,skin_p]);t1=np.concatenate([tt,skin_t+len(pp)]);c1=np.concatenate([cc,np.tile([.2,.2,.2],(len(skin_t),1))]);folder=a.out/str(face_id);folder.mkdir(exist_ok=True);np.savez(folder/'geometry.npz',positions_mm=p1,triangles=t1,triangle_srgb=c1,unit_ids=np.full(len(t1),d['unit_ids'][0],dtype=np.uint32),source_face_ids=np.zeros(len(t1),dtype=np.uint32));w=GlbWriter('base/panel-trial',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; explicit native profile replacement'});w.add_node('source-unit-4268930',p1/1000,t1,[','.join(map(str,col)) for col in c1],extras={'source_unit_id':4268930,'inspection_only':True});w.write(folder/'visual.glb');r={'source_face_id':face_id,'signed_depth_mm':depth,'before_triangles':len(t),'after_triangles':len(t1),'profile':profile,'clip':proof,'skin_native':native,'skin_lod':lod,'geometry_sha256':digest(folder/'geometry.npz'),'visual_sha256':digest(folder/'visual.glb')};report['stages'].append(r);print(face_id,len(t),'->',len(t1),'removed',len(proof['removed_input_triangle_indices']),'partial',len(proof['partial_triangles']),flush=True)
        # Keep each proposal independent until its external appearance is reviewed.
        report['producer_sha256']={str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_panel_replace.py']};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
