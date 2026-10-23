# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Extract large native cylindrical supports without changing CAD."""
import sys,json,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.TopoDS import TopoDS
sp=importlib.util.spec_from_file_location('comp',ROOT/'benchmarks/2026-10-17-composed-pipeline/run.py');comp=importlib.util.module_from_spec(sp);sp.loader.exec_module(comp)
r={}
for cid in ['technology-core/arm-and-shared','technology-core/pedestal-and-shoulder','energy-unit/unit']:
 path=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step';d,reader,faces,shells,owners=comp.native(path);rows=[]
 for i in range(1,faces.Extent()+1):
  s=BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(i)))
  if s.GetType()!=GeomAbs_Cylinder:continue
  c=s.Cylinder();rr=c.Radius()
  if rr<20:continue
  v=c.Axis().Direction();a=c.Axis().Location();rows.append({'face':i,'shell':owners[i],'radius':rr,'axis':[v.X(),v.Y(),v.Z()],'anchor':[a.X(),a.Y(),a.Z()]})
 r[cid]={'path':str(path),'sha256':comp.digest(path),'cylinders':rows};print(cid,len(rows),flush=True)
(ROOT/'out/rmuc2027-curve-trial/native-supports.json').write_text(json.dumps(r,indent=2))
