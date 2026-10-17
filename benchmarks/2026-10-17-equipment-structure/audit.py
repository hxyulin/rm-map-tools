#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only native surface/feature inventory for the two structural shells."""
import argparse,collections,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from cad_detail_passes import small_bore_groups,area
from cad_wall_fill import shape_map
from mesh_parts import tessellate
from plan_cad_lods import digest
from validate_parts import read_part
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_FACE,TopAbs_SHELL,TopAbs_WIRE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);results=[]
    for cid in ['dart-station/frame','outpost/fixed/upper-cluster']:
        folder=ROOT/'out/rmuc2027-equipment-pipeline'/cid;prior=json.loads((folder/'native.json').read_bytes())
        if digest(folder/'source.step')!=prior['source_step_sha256']:raise ValueError('source changed')
        doc,reader,error=read_part(str(folder/'source.step'))
        if error:raise ValueError(error)
        labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels);root=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));shell=shape_map(root,TopAbs_SHELL).FindKey(1);faces=shape_map(shell,TopAbs_FACE);records=[];stats={}
        def observe(index,face,count):
            local=faces.FindIndex(face)
            if not local:return
            surface=BRepAdaptor_Surface(face);box=Bnd_Box();BRepBndLib.AddOptimal_s(face,box,False,False);bounds=[[v.X(),v.Y(),v.Z()] for v in [box.CornerMin(),box.CornerMax()]];records.append({'native_face_index':index,'shell_face_index':local,'surface':str(surface.GetType()).split('_')[-1],'triangles':count,'area_mm2':area(face),'inner_wires':max(0,shape_map(face,TopAbs_WIRE).Extent()-1),'bbox_mm':bounds})
        p,t,m,palette=tessellate(doc,.4,.25,stats,observe)
        if len(t)!=prior['native_triangles'] or len(records)!=faces.Extent():raise ValueError('native inventory changed')
        bores=small_bore_groups(shell,maximum_radius_mm=8.499,maximum_depth_mm=25);by_surface=collections.Counter()
        for r in records:by_surface[r['surface']]+=r['triangles']
        result={'id':cid,'source_step_sha256':prior['source_step_sha256'],'native_shell':1,'shell_faces':faces.Extent(),'shell_triangles':sum(r['triangles'] for r in records),'triangles_by_surface':dict(by_surface),'top_faces':sorted(records,key=lambda r:r['triangles'],reverse=True)[:30],'discovered_small_bores':bores,'scope':'Read-only native discovery; face indices scoped to component STEP checksum. Feature size does not establish safe closure or mechanical ownership.'};results.append(result);print(cid,dict(by_surface),'bore candidates',len(bores),flush=True)
    (a.out/'native-audit.json').write_text(json.dumps({'components':results,'producer_sha256':digest(Path(__file__))},indent=2)+'\n')

if __name__=='__main__':main()
