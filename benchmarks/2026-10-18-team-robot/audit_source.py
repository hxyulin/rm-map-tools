# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,json
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from validate_parts import read_part
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.collections import Sequence_TDF_Label,IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.TopoDS import TopoDS_Compound
from OCP.BRep import BRep_Builder
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
parser=argparse.ArgumentParser(description='Audit source occurrence ownership and recover the original cooked-mesh centre.')
parser.add_argument('--sources',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('name')
args=parser.parse_args()
folder=args.out;folder.mkdir(parents=True,exist_ok=True);name=args.name
doc,reader,error=read_part(str(args.sources/(name+'.step')));assert error is None
st=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main());roots=Sequence_TDF_Label();st.GetFreeShapes(roots)
comp=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(comp)
for i in range(1,roots.Length()+1):builder.Add(comp,st.GetShape_s(roots.Value(i)))
solids=ShapeMap();TopExp.MapShapes_s(comp,TopAbs_SOLID,solids)
def label_name(label):
 n=TDataStd_Name()
 return n.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(),n) else '?'
rows=[]
def walk(label,location,path):
 d=TDF_Label()
 if st.GetReferredShape_s(label,d):location=location.Multiplied(st.GetLocation_s(label))
 else:d=label
 node={'path':path,'name':label_name(d),'occurrence_name':label_name(label)}
 children=Sequence_TDF_Label();st.GetComponents_s(d,children)
 if children.Length():
  node['children']=[path+'/'+str(i) for i in range(1,children.Length()+1)]
  rows.append(node)
  for i in range(1,children.Length()+1):walk(children.Value(i),location,path+'/'+str(i))
 else:
  shape=st.GetShape_s(d).Moved(location);local=ShapeMap();TopExp.MapShapes_s(shape,TopAbs_SOLID,local)
  node['native_solids']=[solids.FindIndex(local.FindKey(i)) for i in range(1,local.Extent()+1)]
  box=Bnd_Box();BRepBndLib.AddOptimal_s(shape,box,False,False)
  if not box.IsVoid():
   lo,hi=box.CornerMin(),box.CornerMax();node['bounds_mm']=[lo.X(),lo.Y(),lo.Z(),hi.X(),hi.Y(),hi.Z()]
  tr=location.Transformation();node['placement']=[[tr.Value(i,j) for j in range(1,5)] for i in range(1,4)]
  rows.append(node)
for i in range(1,roots.Length()+1):walk(roots.Value(i),TopLoc_Location(),str(i))
(folder/(name+'-hierarchy.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
for row in rows:
 if row['path'].count('/')<=3:print(row['path'],row['name'],len(row.get('children',[])),'solids',row.get('native_solids',[]),flush=True)

from mesh_parts import tessellate
p,t,c,palette=tessellate(doc,.25,.3)
(folder/(name+"-frame.json")).write_text(json.dumps({"source_center_mm":((p.min(0)+p.max(0))/2).tolist()}))
print("frame done",flush=True)
