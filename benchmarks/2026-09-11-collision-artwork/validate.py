"""Verify pins, bindings, unchanged visuals, and sampled arena ground heights."""
import json
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from gltf_scene import read_glb,mesh_instances,write_glb
from collision_artwork import strip
from simplify_package import check_bindings,digest,scene_triangles
before=Path('../rm-simulator/local-assets/field');after=Path('out/collision-artwork-candidate')
report={'assets':{},'visuals_unchanged':True}
for scope in ['', 'equipment']:
 old=json.loads((before/scope/'manifest.json').read_text());new=json.loads((after/scope/'manifest.json').read_text())
 art=new.get('articulation');bindings=json.loads((after/scope/art['file']).read_text()) if art else None
 if art:assert digest(after/scope/art['file'])==art['sha256']
 for name,e in new['assets'].items():
  assert digest(before/scope/old['assets'][name]['visual'])==digest(after/scope/e['visual'])==e['visual_sha256']
  assert digest(after/scope/e['collision'])==e['collision_sha256']
  d,b=read_glb(after/scope/e['collision']);od,_=read_glb(before/scope/old['assets'][name]['collision'])
  if bindings:
   binding=bindings['assets'].get(name,{}).get('files',{}).get('collision')
   if binding:assert binding['sha256']==e['collision_sha256'];check_bindings(d,binding)
  report['assets'][name]=dict(before=scene_triangles(od),after=scene_triangles(d),instances=max(1,len(e.get('placements_in_source_arena_frame',[]))))
def locator(path):
 d,b=read_glb(path);ps=[];ts=[];offset=0;names=[]
 for ni,_,p,t,_ in mesh_instances(d,b):ps.append(p);ts.append(t+offset);offset+=len(p);names.extend([d['nodes'][ni].get('name')]*len(t))
 p=np.vstack(ps);t=np.vstack(ts)
 poly=vtk.vtkPolyData();points=vtk.vtkPoints();points.SetData(numpy_to_vtk(p,deep=True));poly.SetPoints(points)
 cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(t),3),t]).astype(np.int64).ravel(),deep=True));poly.SetPolys(cells)
 loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();loc.names=names
 return loc,p.min(0),p.max(0)
d,bin=read_glb(before/'arena-static-collision.glb')
removed=json.loads((after/'manifest.json').read_text())['assets']['arena-static']['collision_artwork_removed']['removed']
d,bin,_=strip(d,bin,[dict(node=r['node'],material=r['material']) for r in removed])
write_glb(after/'arena-stripped-reference.glb',d,bin)
a,lo,hi=locator(after/'arena-stripped-reference.glb');b,_,_=locator(after/'arena-static-collision.glb')
xyz=[0.,0.,0.];pc=[0.,0.,0.];t=vtk.mutable(0.);sub=vtk.mutable(0);cellid=vtk.mutable(0);cell=vtk.vtkGenericCell()
deltas=[];hits_changed=0;samples=0;outliers=[]
for x in np.arange(lo[0]+.071,hi[0],.15):
 for y in np.arange(lo[1]+.093,hi[1],.15):
  values=[];nodes=[]
  for loc in [a,b]:
   hit=loc.IntersectWithLine([x,y,hi[2]+1],[x,y,lo[2]-1],1e-9,t,xyz,pc,sub,cellid,cell)
   values.append(xyz[2] if hit else None);nodes.append(loc.names[int(cellid)] if hit else None)
  samples+=1
  if (values[0] is None)!=(values[1] is None):hits_changed+=1
  elif values[0] is not None:
   delta=abs(values[1]-values[0]);deltas.append(delta)
   if delta>.008:outliers.append(dict(x=float(x),y=float(y),heights=values,nodes=nodes))
report['ground_outliers']=outliers
report['ground_samples']=dict(rays=samples,both_hit=len(deltas),hit_status_changes=hits_changed,max_height_delta_mm=float(max(deltas)*1000),p99_height_delta_mm=float(np.percentile(deltas,99)*1000),over_8mm=int((np.array(deltas)>.008).sum()))
(after/'collision-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
