#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Count current triangles lying on native planes; no finite-face ownership claim."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from validate_parts import read_part
from cad_wall_fill import shape_map
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;r=json.loads((out/'summary.json').read_bytes());audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());src=out/'source.step'
    if digest(src)!=audit['component_step_sha256']:raise ValueError('source mismatch')
    doc,reader,error=read_part(str(src))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);faces=shape_map(XCAFDoc_ShapeTool.GetShape_s(roots.Value(1)),TopAbs_FACE);current=np.load(ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz');report={'plane_tolerance_mm':.01,'scope':'Current triangle classification against original supporting planes and expanded face AABBs. Not original finite-face correspondence; triangles may bridge filled holes. Unmatched includes curved facets, changed relief and numerical seams.','units':[]}
    for u in r['units']:
        source=u['source_unit_id'];index=next(i for i,x in enumerate(audit['units']) if x['source_id']==source);mask=current['unit_ids']==index;tri=current['positions_mm'][current['triangles'][mask]];colors=current['triangle_srgb'][mask];normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(normals,axis=1)/2;normals/=np.maximum(2*area[:,None],1e-20);groups={}
        for f in u['source_planar_faces']:
            plane=BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(f['native_face_index']))).Plane();n=np.array([plane.Axis().Direction().X(),plane.Axis().Direction().Y(),plane.Axis().Direction().Z()]);o=np.array([plane.Location().X(),plane.Location().Y(),plane.Location().Z()]);distance=float(n@o)
            if n[np.argmax(abs(n))]<0:n=-n;distance=-distance
            key=tuple(np.round(np.r_[n,distance],5));group=groups.setdefault(key,{'normal':n,'offset':distance,'source_faces':[]});group['source_faces'].append(f)
        matched=np.zeros(len(tri),bool);rows=[]
        for g in groups.values():
            support=(np.abs(normals@g['normal'])>1-1e-7)&(~matched);ids=np.flatnonzero(support)
            if not len(ids):continue
            residual=np.abs(tri[ids]@g['normal']-g['offset']).max(1);ids=ids[residual<=.01]
            if not len(ids):continue
            finite=np.zeros(len(ids),bool)
            for f in g['source_faces']:
                bb=np.array(f['bbox_mm']);finite|=(tri[ids].min(1)>=bb[0]-.01).all(1)&(tri[ids].max(1)<=bb[1]+.01).all(1)
            ids=ids[finite]
            if not len(ids):continue
            matched[ids]=True;rows.append({'current_triangles':len(ids),'current_area_mm2':float(area[ids].sum()),'source_face_ids':[f['source_face_id'] for f in g['source_faces']],'source_inner_loops':sum(len(f['inner_loops']) for f in g['source_faces']),'normal':g['normal'].tolist(),'plane_offset_mm':g['offset']})
        row={'source_unit_id':source,'current_triangles':len(tri),'on_source_supporting_planes_triangles':int(matched.sum()),'on_source_supporting_planes_area_fraction':float(area[matched].sum()/area.sum()),'unmatched_triangles':int((~matched).sum()),'planes':sorted(rows,key=lambda x:x['current_triangles'],reverse=True)};report['units'].append(row);print(source,'plane triangles',row['on_source_supporting_planes_triangles'],'other',row['unmatched_triangles'],'plane area',row['on_source_supporting_planes_area_fraction'],flush=True)
        np.savez(out/str(source)/'support-classification.npz',on_source_plane=matched)
    report['producer_sha256']=digest(Path(__file__));(out/'support-cost.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
