# SPDX-License-Identifier: MIT OR Apache-2.0
import sys,json,collections,time
from pathlib import Path
sys.path.insert(0,str(Path('python').resolve()))
from validate_parts import read_part
import mesh_parts
from OCP.BRepAdaptor import BRepAdaptor_Surface
parts=json.load(open('out/v12/parts.json'))['parts'];part=next(p for p in parts if p['name']=='7000001_1_ASM')
doc,rd,err=read_part(str(Path('out/v12')/part['file']));assert not err,err
original=mesh_parts.face_meshes
counts=collections.defaultdict(lambda:dict(faces=0,triangles=0,recovery_faces=0,recovery_triangles=0));largest=[]
def wrap(face,lin,ang,stats):
 before=dict(stats);items=original(face,lin,ang,stats);n=sum(t.NbTriangles() for _,t,_ in items)
 kind=str(BRepAdaptor_Surface(face).GetType()).split('.')[-1];r=counts[kind];r['faces']+=1;r['triangles']+=n
 recovery=any(stats.get(k,0)>before.get(k,0) for k in ['fine_retries','split_retries','analytic_bands','narrow_face_retries'])
 if recovery:r['recovery_faces']+=1;r['recovery_triangles']+=n
 largest.append(dict(surface=kind,triangles=n,recovery=recovery))
 return items
mesh_parts.face_meshes=wrap
mesh=mesh_parts.tessellate(doc,4,0.5)
result=dict(part=part['name'],linear_deflection_mm=4,angular_deflection_rad=0.5,triangles=len(mesh[1]),surfaces=dict(counts),largest_faces=sorted(largest,key=lambda x:-x['triangles'])[:20])
Path('benchmarks/2026-09-11-tessellation-presets/resource-zone-face-profile.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
