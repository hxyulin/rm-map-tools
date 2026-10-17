#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Inspect actual native planar trim complexity of the Base's costliest faces."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from validate_parts import read_part
from cad_wall_fill import shape_map
from plan_cad_lods import digest
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.TopAbs import TopAbs_FACE,TopAbs_WIRE,TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def main():
    out=Path(sys.argv[1]);audit=json.loads((out/'audit.json').read_bytes())
    if digest(out/'source.step')!=audit['component_step_sha256']:raise ValueError('Base input changed')
    doc,_,error=read_part(str(out/'source.step'))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots)
    shape=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(shape,TopAbs_FACE)
    if faces.Extent()!=audit['native_faces']:raise ValueError('face inventory changed')
    selected=sorted((f for f in audit['faces'] if f['surface']=='Plane'),key=lambda f:f['triangles'],reverse=True)[:20];result=[]
    for record in selected:
        f=TopoDS.Face(faces.FindKey(record['native_face_index']));plane=BRepAdaptor_Surface(f).Plane();outer=BRepTools.OuterWire_s(f)
        props=GProp_GProps();BRepGProp.SurfaceProperties_s(BRepBuilderAPI_MakeFace(plane,outer,True).Face(),props)
        result.append({**record,'inner_wires':shape_map(f,TopAbs_WIRE).Extent()-1,'outer_wire_edges':shape_map(outer,TopAbs_EDGE).Extent(),
                       'outer_profile_area_mm2':props.Mass(),'removed_trim_area_fraction':1-record['area_mm2']/props.Mass()})
    report={'component_step_sha256':audit['component_step_sha256'],'source_faces':result,'scope':'Read-only planar trim inventory; inner wires may be functional openings, not removable by classification alone.','producer_sha256':digest(Path(__file__))}
    (out/'trim-analysis.json').write_text(json.dumps(report,indent=2)+'\n')
    for r in result[:6]:print(r['source_face_id'],r['triangles'],'triangles;',r['inner_wires'],'inner wires;',r['outer_wire_edges'],'outer edges',flush=True)
if __name__=='__main__':main()
