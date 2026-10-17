#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build explicit source-outline visual backing plates, retaining source members."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_surface_lods import profile_prism,material_lod
from cad_detail_passes import mesh_native_detail
from cad_planar_shell import planar_skin
from cad_wall_fill import shape_map
from validate_parts import read_part
from plan_cad_lods import digest
from export_field_package import GlbWriter
from mesh_quality import deviation
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(exist_ok=True,parents=True);source=ROOT/'out/rmuc2027-base-structure-audit/source.step';audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());reference=ROOT/'out/rmuc2027-base-shells-audit/baseline.npz';d=np.load(reference)
    if digest(source)!=audit['component_step_sha256']:raise ValueError('native source mismatch')
    doc,reader,error=read_part(str(source))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);faces=shape_map(XCAFDoc_ShapeTool.GetShape_s(roots.Value(1)),TopAbs_FACE);lookup={f['source_face_id']:f for f in audit['faces']};report={'source_step_sha256':digest(source),'reference_sha256':digest(reference),'units':[],'scope':'Explicit source-outline plate approximations for four backing shells; 15 mm sampled visual budget. Removes ribs/posts/recesses and strictly sub-17 mm apertures. Original STEP, source ownership, detectors and installed assets unchanged.'}
    for source_id,face_id in [(4756187,4744482),(4664029,4652734),(4693907,4682612),(4723785,4712490)]:
        i=next(i for i,u in enumerate(audit['units']) if u['source_id']==source_id);mask=d['unit_ids']==i;palette=np.unique(d['triangle_srgb'][mask],axis=0)
        if len(palette)!=1:raise ValueError('backing is not single-material')
        face=faces.FindKey(lookup[face_id]['native_face_index']);shape,proof=profile_prism(face,depth_mm=1.5,maximum_gap_mm=17);p,t,_,_,meshproof=mesh_native_detail(shape,[','.join(map(str,palette[0]))]*shape_map(shape,TopAbs_FACE).Extent(),linear_deflection_mm=.1,angular_deflection_rad=.6);p,t,_,skin=planar_skin(p,t,np.zeros(len(t),int));p,t,_,lod=material_lod(p,t,np.zeros(len(t),int),error_mm=1,sampled_limit_mm=3,sample_count=16384);old=d['positions_mm'][d['triangles'][mask]];quality=deviation(old.reshape(-1,3),np.arange(len(old)*3).reshape(-1,3),p,t,count=16384)
        if quality['max']>15:raise ValueError('backing exceeds explicit 15 mm profile budget')
        folder=a.out/str(source_id);folder.mkdir(exist_ok=True);np.savez(folder/'geometry.npz',positions_mm=p,triangles=t,triangle_srgb=np.tile(palette[0],(len(t),1)),unit_ids=np.full(len(t),i,dtype=np.uint32),source_face_ids=np.zeros(len(t),dtype=np.uint32));w=GlbWriter('base/backing-profile',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; source-outline backing plate approximation'});w.add_node('source-unit-'+str(source_id),p/1000,t,[','.join(map(str,palette[0]))]*len(t),extras={'source_unit_id':source_id,'inspection_only':True});w.write(folder/'visual.glb');report['units'].append({'source_unit_id':source_id,'source_face_id':face_id,'before_triangles':int(mask.sum()),'after_triangles':len(t),'native_profile':proof,'native_meshing':meshproof,'skin':skin,'plate_lod':lod,'sampled_deviation_mm':quality,'visual_sha256':digest(folder/'visual.glb'),'geometry_sha256':digest(folder/'geometry.npz')});print(source_id,int(mask.sum()),'->',len(t),quality,flush=True)
    report['producer_sha256']={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_planar_shell.py',ROOT/'python/cad_surface_lods.py']};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
