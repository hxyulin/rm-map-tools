#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only OCCT cylinder/part audit for source-qualified articulation recipes.

Face, solid and shell ordinals are OCCT import ordinals, never original STEP IDs.
All coordinates are source millimetres; no healing, tessellation or repair pass.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def audit(path, minimum_radius_mm=5.):
    from validate_parts import read_part
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.collections import Sequence_TDF_Label, IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
    from OCP.TopoDS import TopoDS_Compound, TopoDS
    from OCP.BRep import BRep_Builder
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    document, reader, error = read_part(str(path))
    if error: raise ValueError(error)
    st = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots=Sequence_TDF_Label();st.GetFreeShapes(roots)
    shape=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(shape)
    for i in range(1, roots.Length()+1):builder.Add(shape,st.GetShape_s(roots.Value(i)))
    maps={}
    for name,kind in [('solid',TopAbs_SOLID),('shell',TopAbs_SHELL),('face',TopAbs_FACE)]:
        m=ShapeMap();TopExp.MapShapes_s(shape,kind,m);maps[name]=m
    owners={}
    for kind in ['shell','solid']:
        for i in range(1,maps[kind].Extent()+1):
            faces=ShapeMap();TopExp.MapShapes_s(maps[kind].FindKey(i),TopAbs_FACE,faces)
            for j in range(1,faces.Extent()+1):
                owners.setdefault(maps['face'].FindIndex(faces.FindKey(j)),{})[kind]=i
    cylinders=[]
    for i in range(1,maps['face'].Extent()+1):
        face=TopoDS.Face(maps['face'].FindKey(i));surface=BRepAdaptor_Surface(face)
        if surface.GetType()!=GeomAbs_Cylinder:continue
        c=surface.Cylinder()
        if c.Radius()<minimum_radius_mm:continue
        axis=c.Axis();p=axis.Location();v=axis.Direction()
        direction=np.array([v.X(),v.Y(),v.Z()]);point=np.array([p.X(),p.Y(),p.Z()])
        if direction[np.argmax(np.abs(direction))]<0:direction=-direction
        line=point-direction*np.dot(point,direction)
        box=Bnd_Box();BRepBndLib.AddOptimal_s(face,box,False,False)
        cylinders.append(dict(face=i,**owners.get(i,{}),radius_mm=c.Radius(),
            point_mm=point.tolist(),axis=direction.tolist(),line_mm=line.tolist(),bounds_mm=[box.CornerMin().X(),box.CornerMin().Y(),box.CornerMin().Z(),box.CornerMax().X(),box.CornerMax().Y(),box.CornerMax().Z()]))
    return dict(source_file=Path(path).name,source_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        coordinate_contract='source millimetres; OCCT import ordinals, not STEP entity IDs',
        counts={k:m.Extent() for k,m in maps.items()},cylinders=cylinders)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('step',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--minimum-radius-mm',type=float,default=5.);a=p.parse_args()
    result=audit(a.step,a.minimum_radius_mm);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(file=str(a.step),counts=result['counts'],cylinders=len(result['cylinders']))))

if __name__=='__main__':main()
