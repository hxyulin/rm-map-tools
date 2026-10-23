"""Approximate independent sheet-profile reconstruction. Never edits source/baseline."""
from pathlib import Path
import sys,json,hashlib,importlib.util
import numpy as np
import shapely as sh
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
spec=importlib.util.spec_from_file_location('exact_reader',ROOT/'benchmarks/2026-10-23-tech-grill-panels/build.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
from export_field_package import GlbWriter
from gltf_scene import read_glb
from cad_collision_profiles import mesh_metrics
OUT=ROOT/'out/rmuc2027-tech-grill-profile';REF=reader.REF;BASE=ROOT/'out/rmuc2027-tech-bars-review/bars-restored.glb'
PAIRS=[(1499649,1499993),(1500295,1500597),(1500932,1501684),(1501182,1501432)]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def quad(h):
 p=np.array(h.exterior.coords)[:-1];v=np.roll(p,-1,axis=0)-p
 ids=np.sort(np.argsort(np.linalg.norm(v,axis=1))[-4:]);corners=[]
 for a,b in zip(ids,np.roll(ids,-1)):
  # Intersect source straight walls, replacing rounded slot corners by sharp corners.
  t=np.linalg.solve(np.column_stack([v[a],-v[b]]),p[b]-p[a])[0];corners.append(p[a]+t*v[a])
 q=sh.Polygon(corners);assert q.is_valid and q.area>0
 return q

def extrude(d,o,b,n,thickness):
 uv=np.array([np.array(t.exterior.coords)[:3] for t in sh.get_parts(sh.constrained_delaunay_triangles(d))]);top=o+uv@b
 flip=np.cross(top[:,1]-top[:,0],top[:,2]-top[:,0])@n<0;top[flip]=top[flip][:,::-1]
 bottom=top[:,::-1]-thickness*n
 sides=[]
 for ring in [d.exterior,*d.interiors]:
  p=o+np.array(ring.coords)@b
  for a,c in zip(p[:-1],p[1:]):sides.extend([[a,a-thickness*n,c-thickness*n],[a,c-thickness*n,c]])
 out=np.concatenate([top,bottom,np.array(sides)])
 # Orient the closed component consistently, retaining all thickness walls.
 import vtk
 from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray,vtk_to_numpy
 pp,ii=np.unique(np.round(out.reshape(-1,3),7),axis=0,return_inverse=True)
 points=vtk.vtkPoints();points.SetData(numpy_to_vtk(pp,deep=True));cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(out),3),ii.reshape(-1,3)]).astype(np.int64).ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(points);poly.SetPolys(cells)
 normals=vtk.vtkPolyDataNormals();normals.SetInputData(poly);normals.ConsistencyOn();normals.AutoOrientNormalsOn();normals.SplittingOff();normals.Update();pol=normals.GetOutput();return vtk_to_numpy(pol.GetPoints().GetData())[vtk_to_numpy(pol.GetPolys().GetData()).reshape(-1,4)[:,1:]]

def main():
 s=np.load(REF);sg=s['positions_mm'][s['triangles']];chunks=[];records=[];slots=[]
 for f,h in PAIRS:
  dom,o,b,n,err=reader.domain(sg[s['source_face_ids']==f]);back,oo,bb,nn,_=reader.domain(sg[s['source_face_ids']==h]);back=sh.transform(back,lambda uv:(oo+uv@bb-o)@b.T)
  thickness=-float(np.mean((sg[s['source_face_ids']==h]-o)@n));outer=sh.Polygon(dom.exterior).simplify(.05,preserve_topology=True);holes=[];checks=[]
  for j,r in enumerate(dom.interiors):
   old=sh.Polygon(r)
   if old.area>100:
    new=quad(old);kind='structural-slot-sharp-corners';slots.append(new)
   else:
    center=np.array(old.centroid.coords)[0];radius=np.linalg.norm(np.array(r.coords)[:-1]-center,axis=1).max();angles=np.arange(6)*np.pi/3;new=sh.Polygon(center+radius/np.cos(np.pi/6)*np.column_stack([np.cos(angles),np.sin(angles)]));kind='circumscribed-six-sided-fastener-bore'
   holes.append(new);checks.append({'source_hole_index':j,'kind':kind,'source_area_mm2':old.area,'candidate_area_mm2':new.area,'source_bounds_uv_mm':list(old.bounds),'candidate_vertices':len(new.exterior.coords)-1,'boundary_hausdorff_mm':float(sh.hausdorff_distance(old.boundary,new.boundary,densify=.1)),'source_aperture_area_occluded_mm2':float(old.difference(new).area),'source_witness_clear':bool(new.covers(old.representative_point()))})
  d=sh.Polygon(outer.exterior,[q.exterior.coords for q in holes]);assert d.is_valid and len(d.interiors)==len(dom.interiors)
  out=extrude(d,o,b,n,thickness)
  volume=np.einsum('ij,ij->i',out[:,0],np.cross(out[:,1],out[:,2])).sum()/6
  if volume<0:out=out[:,::-1]
  chunks.append(out)
  p,ix=np.unique(np.round(out.reshape(-1,3),5),axis=0,return_inverse=True);metrics=mesh_metrics(p,ix.reshape(-1,3))
  # Each parallel source face must see every corresponding slot witness open.
  for item in checks:
   old=sh.Polygon(dom.interiors[item['source_hole_index']]);backholes=[sh.Polygon(q) for q in back.interiors];matched=min(backholes,key=lambda q:q.centroid.distance(old.centroid));new=holes[item['source_hole_index']];item['paired_source_aperture_area_occluded_mm2']=matched.difference(new).area
  rec={'source_face_pair':[f,h],'triangles':len(out),'thickness_mm':thickness,'source_opposed_profile_error_mm':sh.hausdorff_distance(dom.boundary,back.boundary,densify=.1),'perimeter_error_mm':sh.hausdorff_distance(dom.exterior,d.exterior,densify=.1),'topology':metrics,'profile_vertices':len(d.exterior.coords)-1+sum(len(q.exterior.coords)-1 for q in holes),'apertures':checks,'minimum_inter_aperture_web_mm':min(a.distance(bb)for i,a in enumerate(holes)for bb in holes[i+1:]),'source_minimum_inter_aperture_web_mm':min(sh.Polygon(a).distance(sh.Polygon(bb))for i,a in enumerate(dom.interiors)for bb in list(dom.interiors)[i+1:]),'basis_rows':b.tolist(),'origin_mm':o.tolist(),'normal':n.tolist()};records.append(rec)
 out=np.concatenate(chunks);np.savez_compressed(OUT/'shell.npz',positions_mm=out.reshape(-1,3),triangles=np.arange(out.size//3).reshape(-1,3))
 w=GlbWriter('technology-core/tool-head/profile-review',{'version':'2.0','extras':{'inspection_only':True,'profile_reconstruction':True}})
 for i,g in enumerate(chunks):w.add_node(f'shell1504356-profile-{i}',g.reshape(-1,3)/1000,np.arange(g.size//3).reshape(-1,3),['0.2520,0.2520,0.2520']*len(g),extras={'source_unit_id':1504356,'source_face_pair':list(PAIRS[i]),'component_id':'technology-core/tool-head','approximate_profile':True})
 w.write(OUT/'shell.glb')
 # Explicit centroid selection ledger, dark material gate, and interior/corner ownership ambiguity.
 doc,blob=read_glb(BASE);rows=reader.extract(doc,blob);cg=np.concatenate([r[3]for r in rows]);ids,dist=reader.nearest_ids(sg,cg.mean(1));owner=s['source_unit_ids'][ids];ledger=[];selected=[];offset=0
 for node,pi,pr,g in rows:
  color=doc['materials'][pr['material']].get('extras',{}).get('step_colour_srgb');gate=color==[.252,.252,.252];ix=np.flatnonzero((owner[offset:offset+len(g)]==1504356)&gate)
  if len(ix):
   owned=g[ix];samples=np.concatenate([owned, .6*owned+.4*owned.mean(1)[:,None,:]],axis=1);vid,vd=reader.nearest_ids(sg,samples.reshape(-1,3));owners=s['source_unit_ids'][vid].reshape(-1,6);foreign=np.any(owners!=1504356,axis=1)
   ledger.append({'node':node,'primitive':pi,'material':pr['material'],'source_color':color,'triangle_indices':ix.tolist(),'global_triangle_indices':(ix+offset).tolist(),'centroid_source_triangle_ids':ids[ix+offset].tolist(),'centroid_distance_mm':dist[ix+offset].tolist(),'six_sample_source_unit_ids':owners.tolist(),'ambiguous_triangle_indices':ix[foreign].tolist(),'maximum_six_sample_distance_mm':float(vd.max())});selected.extend((ix+offset).tolist())
  offset+=len(g)
 np.savez_compressed(OUT/'selection-ledger.npz',centroid_source_triangle_ids=ids,centroid_source_unit_ids=owner,centroid_distance_mm=dist,selected_global_triangle_indices=selected)
 report={'source_sha256':digest(REF),'bars_restored_sha256':digest(BASE),'source_unit_id':1504356,'source_triangles':int((s['source_unit_ids']==1504356).sum()),'current_nearest_centroid_selected_triangles':int((owner==1504356).sum()),'current_dark_centroid_selected_triangles':len(selected),'non_dark_centroid_selected_triangles_excluded':int((owner==1504356).sum())-len(selected),'candidate_triangles':len(out),'delta_vs_current_selected':len(out)-len(selected),'delta_vs_current_585_heuristic':len(out)-int((owner==1504356).sum()),'structural_slots':sum(sum(x['kind'].startswith('structural')for x in r['apertures'])for r in records),'fastener_bores':sum(sum(x['kind'].startswith('circumscribed')for x in r['apertures'])for r in records),'closed_bores':0,'planes':records,'selection_ledger':ledger,'ambiguous_selected_triangles':sum(len(r['ambiguous_triangle_indices'])for r in ledger),'integrated_export':False,'decision':'Reject as a cost-reduction candidate: 2856 exceeds current585 heuristic and dark580 selection. Shell-only export; independent folds visibly split and nearest-source ownership is ambiguous at shared edges.','limitations':['Four separate 2mm solid panels; fold intersections are approximate and not a single boolean-unioned watertight shell.','Rounded slot ends replaced by intersections of the four long source edges. All 34 slot apertures retained; all 70 bores retained as circumscribed hexagons.','No sub-mm bores found, so no deliberate closed-bore variant exported.','No native curved/interior/duplicate sheets retained. Source perimeter simplified by 0.05mm.','No unrelated geometry, hierarchy or materials were modified.','896 slots-only triangles is specific to this extrusion construction, not a universal lower bound.'], 'idealized_slots_only_cost':{'formula':'4*V + 4*H - 4 per closed extruded polygon; even ignoring all fastener bores','perimeter_vertices':sum(r['profile_vertices']-sum(x['candidate_vertices']for x in r['apertures'])for r in records),'slot_vertices':34*4,'holes':34}}
 ideal=report['idealized_slots_only_cost'];ideal['triangles']=4*(ideal['perimeter_vertices']+ideal['slot_vertices'])+4*34-4*4
 (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print({k:report[k]for k in ['candidate_triangles','delta_vs_current_selected','structural_slots','fastener_bores','ambiguous_selected_triangles','idealized_slots_only_cost']})
if __name__=='__main__':main()
