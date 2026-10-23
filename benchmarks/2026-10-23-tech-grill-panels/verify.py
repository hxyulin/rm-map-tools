"""Reopen and independently compare every aperture of the source-owned candidate."""
from pathlib import Path
import json,sys
import numpy as np
import shapely as sh
from scipy.optimize import linear_sum_assignment
from build import ROOT,OUT,REF,BASE,domain,topology,digest,extract
from export_field_package import GlbWriter
from gltf_scene import read_glb,read_glb_nodes
from mesh_quality import distances
from cad_collision_profiles import mesh_metrics
FACES=[1499649,1499993,1500295,1500597,1500932,1501182,1501432,1501684]
def main():
 src=np.load(REF);sg=src['positions_mm'][src['triangles']];q=np.load(OUT/'boundary-0.05mm/shell.npz');g=q['positions_mm'][q['triangles']];rep=json.load(open(OUT/'report.json'));cl=np.load(OUT/'current-classification.npz');d,b=read_glb(BASE);cg=np.concatenate([r[3]for r in extract(d,b)]);closest_faces=src['source_face_ids'][cl['source_triangle_ids']]
 w=GlbWriter('technology-core/tool-head/slotted-panels',{'version':'2.0','extras':{'inspection_only':True,'boundary_tolerance_mm':.05}})
 rows=[]
 for f in FACES:
  sm=src['source_face_ids']==f;qm=q['source_face_ids']==f;old=sg[sm];new=g[qm];dom,o,basis,n,err=domain(old);built,_,_,_,_=domain(new);holes=[sh.Polygon(r)for r in dom.interiors]
  # Reproject actual candidate into the SOURCE basis for comparison.
  pp,tt=np.unique(np.round(new.reshape(-1,3),8),axis=0,return_inverse=True);nt=tt.reshape(-1,3);ix=np.sort(np.concatenate([nt[:,[0,1]],nt[:,[1,2]],nt[:,[2,0]]]),axis=1);ix,c=np.unique(ix,axis=0,return_counts=True);actual=sh.build_area(sh.multilinestrings((pp[ix[c==1]]-o)@basis.T));assert topology(dom)==topology(actual)
  ah=[sh.Polygon(r)for r in actual.interiors];cost=np.array([[a.centroid.distance(bb.centroid)for bb in ah]for a in holes]);rr,cc=linear_sum_assignment(cost);matches=[]
  for i,j in zip(rr,cc):
   a,bb=holes[i],ah[j];dist=sh.hausdorff_distance(a.boundary,bb.boundary,densify=.25);assert dist<=.050001;assert bb.covers(a.representative_point());assert actual.intersection(a.buffer(-.05001)).area<1e-7
   matches.append({'source_hole_index':int(i),'candidate_hole_index':int(j),'source_area_mm2':a.area,'candidate_area_mm2':bb.area,'boundary_hausdorff_mm':dist,'clear_witness_uv_mm':list(a.representative_point().coords)[0]})
  ci=np.flatnonzero((closest_faces==f)&(np.max(abs((cg-o)@n),axis=1)<1.05));cp=sh.polygons((cg[ci]-o)@basis.T);current=sh.union_all(cp,grid_size=.0001);current_holes=sum(len(part.interiors)for part in sh.get_parts(current)if part.geom_type=='Polygon')
  current_open=[]
  for a in holes:
   witness=a.representative_point();current_open.append(not current.buffer(.001).covers(witness))
  rows.append({'source_face_id':f,'source_triangles':int(sm.sum()),'candidate_triangles':int(qm.sum()),'source_topology':topology(dom),'candidate_topology':topology(actual),'maximum_boundary_error_mm':sh.hausdorff_distance(dom.boundary,actual.boundary,densify=.25),'current_heuristic_triangles':len(ci),'current_heuristic_projected_holes':current_holes,'source_hole_witnesses_open_in_current_heuristic_domain':sum(current_open),'source_hole_count':len(holes),'aperture_checks':matches})
  w.add_node(f'source-shell-1504356/face-{f}',new.reshape(-1,3)/1000,np.arange(new.size//3).reshape(-1,3),[src['palette'][src['material_ids'][sm][0]]]*len(new),extras={'source_unit_id':1504356,'source_face_id':f,'derived_geometry':True})
 w.write(OUT/'boundary-0.05mm/panels.glb')
 # GLB roundtrip geometry and source colour: export uses face-local normals and float32 metres.
 reopened=list(read_glb_nodes(OUT/'boundary-0.05mm/shell.glb'));gg=np.concatenate([p[t]*1000 for _,p,t,_ in reopened]);assert len(gg)==len(g)
 def samp(a):return np.concatenate([a.mean(1),a[:,0],(a[:,0]+a[:,1])/2])
 for label,geom in [('candidate',g),('original',sg[src['source_unit_ids']==1504356])]:
  p,inv=np.unique(np.round(geom.reshape(-1,3),5),axis=0,return_inverse=True);metrics=mesh_metrics(p,inv.reshape(-1,3));metrics['vertices']=len(p);metrics['triangles']=len(geom)
  if label=='candidate':candidate_topology=metrics
  else:original_topology=metrics
 # Check source-shell surfaces only, with bounded deterministic samples.
 a=sg[src['source_unit_ids']==1504356];old_samples=samp(a)[::3];new_samples=samp(g)[::3];fd=distances(old_samples,g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3));rd=distances(new_samples,a.reshape(-1,3),np.arange(a.size//3).reshape(-1,3))
 result={'recommended_candidate':'boundary-0.05mm/shell.glb','panels_only_candidate':'boundary-0.05mm/panels.glb','source_shell_id':1504356,'source_step_sha256':digest(ROOT/'out/rmuc2027-equipment-pipeline/technology-core/tool-head/source.step'),'source_reference_glb_sha256':digest(ROOT/'out/rmuc2027-protected-source-reference/technology-core/tool-head/reference.glb'),'source_npz_sha256':digest(REF),'baseline_sha256':digest(BASE),'original_shell_triangles':12926,'candidate_shell_triangles':len(g),'original_broad_panel_triangles':sum(r['source_triangles']for r in rows),'candidate_broad_panel_triangles':sum(r['candidate_triangles']for r in rows),'total_apertures_in_paired_panel_faces':sum(r['source_hole_count']for r in rows),'distinct_through_apertures':sum(r['source_hole_count']for r in rows)//2,'original_mesh_topology':original_topology,'candidate_mesh_topology':candidate_topology,'sampled_surface_deviation_mm':{'source_to_candidate_max':float(fd.max()),'candidate_to_source_max':float(rd.max()),'samples':len(fd)+len(rd),'continuous_certificate':False},'glb_roundtrip_sampled_deviation_mm':float(distances(samp(gg)[::5],g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3)).max()),'panels':rows,'limitations':['Source shell already has unmatched tessellation edges; per-face simplification is not a watertight solid certificate.','Current nearest-face labels and projected hole counts are diagnostic heuristics, not a safe removal mask.','Candidate is an owned source-shell/panel replacement, not spliced into baseline. Cost exceeds heavily simplified baseline region; no claim of a baseline triangle reduction.','104 paired through-apertures include all 34 large slots and all 70 smaller holes; no aperture omission, hull, or fill operation.']}
 (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n');assert digest(REF)==rep['source_sha256'] and digest(BASE)==rep['baseline_sha256'];print({k:v for k,v in result.items()if k not in ['panels','limitations']})
if __name__=='__main__':main()
