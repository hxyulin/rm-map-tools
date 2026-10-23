"""Inspection-only source-face reconstruction of slotted shell 1504356."""
from pathlib import Path
import sys,json,copy,hashlib
import numpy as np
import shapely as sh
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,accessor,scene_nodes,write_glb
from simplify_package import append_accessor,compact,scene_triangles
from export_field_package import GlbWriter
OUT=ROOT/'out/rmuc2027-tech-grill-panels';REF=ROOT/'out/rmuc2027-protected-source-reference/technology-core/tool-head/reference.npz';BASE=ROOT/'out/rmuc2027-visual-fidelity-review/protected-1mm/tech-core.glb'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def domain(t):
 p,first,inv=np.unique(np.round(t.reshape(-1,3),5),axis=0,return_index=True,return_inverse=True);p=t.reshape(-1,3)[first];ix=inv.reshape(-1,3)
 e=np.sort(np.concatenate([ix[:,[0,1]],ix[:,[1,2]],ix[:,[2,0]]]),axis=1);e,ct=np.unique(e,axis=0,return_counts=True);assert (ct<=2).all();e=e[ct==1]
 n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);a=np.linalg.norm(n,axis=1);n=n[a.argmax()]/a.max();o=t[0,0];x=np.cross(np.eye(3)[abs(n).argmin()],n);x/=np.linalg.norm(x);basis=np.array([x,np.cross(n,x)])
 err=float(abs((t-o)@n).max())
 if err>1e-4:return None
 dom=sh.build_area(sh.multilinestrings((p[e]-o)@basis.T));assert dom.is_valid and abs(dom.area-a.sum()/2)<max(1e-5,dom.area*1e-8)
 return dom,o,basis,n,err

def topology(d):return {'components':len(sh.get_parts(d)),'holes':sum(len(q.interiors)for q in sh.get_parts(d))}
def extract(d,b):
 root=next(i for i,n in enumerate(d['nodes'])if n.get('extras',{}).get('component_id')=='technology-core/tool-head')
 def walk(i):
  yield i
  for j in d['nodes'][i].get('children',[]):yield from walk(j)
 rows=[]
 for i in walk(root):
  n=d['nodes'][i]
  if 'mesh' not in n:continue
  for pi,pr in enumerate(d['meshes'][n['mesh']]['primitives']):
   p=accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000;t=accessor(d,b,pr['indices']).reshape(-1,3);rows.append((i,pi,pr,p[t]))
 return rows

def nearest_ids(sg,c):
 import vtk
 from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
 pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(np.ascontiguousarray(sg.reshape(-1,3)),deep=True));cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(sg),3),np.arange(len(sg)*3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(pts);poly.SetPolys(cells);loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();ids=[];errors=[]
 for p in c:
  cp=[0.,0.,0.];cell,sub,dist=vtk.reference(0),vtk.reference(0),vtk.reference(0.);loc.FindClosestPoint(p,cp,cell,sub,dist);ids.append(int(cell));errors.append(float(dist)**.5)
 return np.array(ids),np.array(errors)

def main():
 s=np.load(REF);g=s['positions_mm'][s['triangles']];selected=s['source_unit_ids']==1504356;d,b=read_glb(BASE);rows=extract(d,b);cg=np.concatenate([r[3]for r in rows]);ids,dist=nearest_ids(g,cg.mean(1));assigned=s['source_unit_ids'][ids];remove=assigned==1504356
 # Classification cross-check: all three corners must remain closest to the selected source shell,
 # apart from shared folding boundaries. Report failures rather than silently broadening scope.
 vertex_ids,vertex_dist=nearest_ids(g,cg[remove].reshape(-1,3));vu=s['source_unit_ids'][vertex_ids].reshape(-1,3)
 np.savez_compressed(OUT/'current-classification.npz',source_triangle_ids=ids,source_unit_ids=assigned,centroid_distance_mm=dist,selected_triangle_indices=np.flatnonzero(remove),selected_corner_source_unit_ids=vu)
 report={'source_sha256':digest(REF),'baseline_sha256':digest(BASE),'source_shell_id':1504356,'source_face_ids':list(map(int,np.unique(s['source_face_ids'][selected]))),'frame':'Original product-local source axes in mm in NPZ; GLB positions /1000 metres. Runtime tool component and child transforms are identity. No arena placement baked.','original_tool_triangles':len(g),'current_tool_triangles':len(cg),'source_selected_triangles':int(selected.sum()),'current_assigned_selected_triangles':int(remove.sum()),'classification':{'method':'nearest exact-source triangle at each current triangle centroid; selected corners separately checked','maximum_centroid_distance_mm':float(dist[remove].max()),'selected_triangles_with_foreign_corner_owner':int(np.any(vu!=1504356,axis=1).sum()),'foreign_corner_source_units':list(map(int,np.unique(vu[vu!=1504356]))),'maximum_corner_distance_mm':float(vertex_dist.max())},'trials':[]}
 print({k:v for k,v in report.items()if k not in ['source_face_ids','trials']},flush=True)
 for tol in [.02,.05,.1,.25]:
  chunks=[];ff=[];mm=[];records=[]
  for f in np.unique(s['source_face_ids'][selected]):
   m=selected&(s['source_face_ids']==f);t=g[m];r=domain(t)
   if r is None:out=t;rec={'source_face_id':int(f),'kind':'curved-source-retained','before':len(t),'after':len(t)}
   else:
    dom,o,basis,n,err=r;panel=dom.simplify(tol,preserve_topology=True);assert topology(panel)==topology(dom)
    faces=sh.get_parts(sh.constrained_delaunay_triangles(panel));uv=np.array([np.array(q.exterior.coords)[:3]for q in faces]);out=o+uv@basis
    if len(out)>len(t):out=t;panel=dom
    flip=np.cross(out[:,1]-out[:,0],out[:,2]-out[:,0])@n<0;out[flip]=out[flip][:,::-1]
    rebuilt=sh.union_all(sh.polygons(np.round((out-o)@basis.T,8)),grid_size=1e-8);areaerr=sh.area(sh.symmetric_difference(rebuilt,sh.set_precision(panel,1e-8)));assert areaerr<max(1e-5,dom.area*1e-8), (int(f),len(t),len(out),dom.area,panel.area,areaerr)
    rec={'source_face_id':int(f),'kind':'planar-boundary-retriangulation','before':len(t),'after':len(out),'topology':topology(dom),'source_plane_error_mm':err,'source_area_mm2':dom.area,'boundary_hausdorff_mm':sh.hausdorff_distance(dom.boundary,panel.boundary,densify=.25),'symmetric_difference_mm2':sh.area(sh.symmetric_difference(dom,panel)),'triangulated_domain_error_mm2':areaerr,'basis_rows':basis.tolist(),'origin_mm':o.tolist(),'normal':n.tolist()}
   chunks.append(out);ff.extend([f]*len(out));mm.extend([s['material_ids'][m][0]]*len(out));records.append(rec)
  out=np.concatenate(chunks);folder=OUT/f'boundary-{tol:g}mm';folder.mkdir(exist_ok=True)
  np.savez_compressed(folder/'shell.npz',positions_mm=out.reshape(-1,3),triangles=np.arange(out.size//3).reshape(-1,3),source_face_ids=ff,source_unit_ids=np.full(len(out),1504356),material_ids=mm,palette=s['palette'])
  w=GlbWriter('technology-core/tool-head/slotted-shell',{'version':'2.0','extras':{'inspection_only':True,'boundary_tolerance_mm':tol}});w.add_node('source-shell-1504356',out.reshape(-1,3)/1000,np.arange(out.size//3).reshape(-1,3),[s['palette'][i]for i in mm],extras={'source_unit_id':1504356,'component_id':'technology-core/tool-head','derived_geometry':True});w.write(folder/'shell.glb')
  trial={'tolerance_mm':tol,'after_shell_triangles':len(out),'delta_vs_assigned_current':len(out)-int(remove.sum()),'faces':records};report['trials'].append(trial);print(tol,len(out),'planar',sum(r['kind'].startswith('planar')for r in records),flush=True)
 (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 assert digest(REF)==report['source_sha256'] and digest(BASE)==report['baseline_sha256']
if __name__=='__main__':main()
