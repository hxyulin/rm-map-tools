#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Isolated native bore-cap trials; never replaces the approved Base payload."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from validate_parts import read_part
from plan_cad_lods import digest
from cad_wall_fill import shape_map
from cad_surface_lods import close_bore_surfaces,material_lod
from cad_detail_passes import mesh_native_detail
from export_field_package import GlbWriter
from mesh_quality import deviation
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());src=out/'source.step'
    if digest(src)!=audit['component_step_sha256']:raise ValueError('source mismatch')
    doc,reader,error=read_part(str(src))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);solids=shape_map(root,TopAbs_SOLID);lookup={}
    for j in range(1,solids.Extent()+1):
        s=solids.FindKey(j);ff=shape_map(s,TopAbs_FACE);lookup[frozenset(faces.FindIndex(ff.FindKey(k)) for k in range(1,ff.Extent()+1))]=s
    by_index={f['native_face_index']:f for f in audit['faces']};current_path=ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz';current=np.load(current_path);report={'source_sha256':digest(src),'reference_sha256':digest(current_path),'trials':[],'producer_sha256':digest(Path(__file__)),'scope':'Isolated visual discovery candidates. Closures intentionally alter small openings. Not adopted, not source-pose/motion equivalence, not installed assets.'}
    for source in (4268930,4527988):
        i=next(i for i,u in enumerate(audit['units']) if u['source_id']==source);indices={f['native_face_index'] for f in audit['faces'] if f['unit']==i};shape=lookup[frozenset(indices)];local=shape_map(shape,TopAbs_FACE);colors=[by_index[faces.FindIndex(local.FindKey(j))]['source_colour'] for j in range(1,local.Extent()+1)]
        derived,ids,proof=close_bore_surfaces(shape,maximum_gap_mm=17)
        p,t,keys,face_ids,meshproof=mesh_native_detail(derived,[colors[j-1] for j in ids],linear_deflection_mm=.1,angular_deflection_rad=.6)
        native_p,native_t=p.copy(),t.copy();palette,mat=np.unique(np.array([key or '0.6275,0.6275,0.6275' for key in keys]),return_inverse=True)
        p,t,m,lod=material_lod(p,t,mat,error_mm=.25,sampled_limit_mm=1,sample_count=8192);rgb=np.array([list(map(float,key.split(','))) for key in palette])[m]
        selected=current['unit_ids']==i;old_t=current['triangles'][selected];used,inv=np.unique(old_t,return_inverse=True);old_p=current['positions_mm'][used];old_t=inv.reshape(-1,3)
        difference=deviation(old_p,old_t,p,t,count=8192)
        folder=out/str(source);folder.mkdir(exist_ok=True);np.savez(folder/'trial.npz',positions_mm=p,triangles=t,triangle_srgb=rgb,unit_ids=np.full(len(t),i,dtype=np.uint32),source_face_ids=np.zeros(len(t),dtype=np.uint32))
        writer=GlbWriter('base/structure-trial',{'version':'2.0','copyright':'DJI / RoboMaster geometry; derived bore-cap investigation'});writer.add_node('source-unit-'+str(source),p/1000,t,[','.join(map(str,c)) for c in rgb],extras={'source_unit_id':source,'inspection_only':True});writer.write(folder/'trial.glb')
        r={'source_unit_id':source,'before_triangles':int(selected.sum()),'after_triangles':len(t),'closed_source_bores':len(proof['closed_bores']),'native_closure':proof,'native_tessellation':meshproof,'lod':lod,'reference_sampled_difference_mm':difference,'geometry_sha256':digest(folder/'trial.npz'),'glb_sha256':digest(folder/'trial.glb')};report['trials'].append(r);(out/'trial-summary.json').write_text(json.dumps(report,indent=2)+'\n');print(source,r['before_triangles'],'->',len(t),'difference',difference,flush=True)
if __name__=='__main__':main()
