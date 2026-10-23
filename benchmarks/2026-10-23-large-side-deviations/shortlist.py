"""Measure individual conservative seam-preserving panels; no combined export."""
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
from investigate import OUT,load_nodes,area_samples,distances
from panel_trial import triangulate,attachments
from profile_trial import loop,rdp

def run():
 r=json.loads((OUT/'measurements.json').read_text());rows=[];cache={}
 for n in r['nodes']:
  if n['asset']!='base':continue
  if n['source']not in cache:cache[n['source']]=load_nodes(Path(n['source']))[2]
  g=cache[n['source']][n['node']];used=set()
  for pi,patch in enumerate(n['patches']):
   b=patch['boundary']
   if b.get('loop_count')!=1 or b['nonmanifold_edges'] or patch['source_triangles']-b['exact_boundary_planar_triangle_budget']<10:continue
   ids=np.array(patch['triangle_indices']);h=g[ids];f=np.array(patch['fit']['axes_columns']);q=h@f[:,:2];cross=(q[:,1,0]-q[:,0,0])*(q[:,2,1]-q[:,0,1])-(q[:,1,1]-q[:,0,1])*(q[:,2,0]-q[:,0,0]);absolute=abs(cross).sum();signed=abs(cross.sum())
   if absolute-signed>max(.01,absolute*1e-6):continue
   xyz,t=triangulate(h,patch['fit'],attachments(g,ids));target=xyz[t]
   if len(t)>=len(h):continue
   def dist(points,to):return distances(points,to.reshape(-1,3),np.arange(len(to)*3).reshape(-1,3))
   fv=dist(np.unique(h.reshape(-1,3),axis=0),target);fs=dist(area_samples(h,20000,41),target);rs=dist(area_samples(target,20000,43),h)
   rec=dict(asset=n['asset'],node=n['node'],source_unit_id=n['node_extras'].get('source_unit_id'),patch_index=pi,source_triangles=len(h),trial_triangles=len(t),hypothetical_savings_per_asset=len(h)-len(t),hypothetical_placed_savings=(len(h)-len(t))*n['placements'],spans_mm=patch['fit']['spans_mm'],area_mm2=patch['fit']['area_mm2'],plane_rms_mm=patch['fit']['rms_mm'],plane_all_vertex_max_mm=patch['fit']['all_vertex_max_mm'],source_all_vertex_to_trial_max_mm=float(fv.max()),source_area_mean_mm=float(fs.mean()),source_area_p99_mm=float(np.quantile(fs,.99)),source_area_sample_max_mm=float(fs.max()),trial_area_sample_max_mm=float(rs.max()),boundary_vertices_kept=patch['boundary']['vertices'],total_retained_vertices=len(xyz),shared_attachment_vertices_kept=len(attachments(g,ids)),boundary_position_error_mm=0.,source_triangle_indices=ids.tolist(),disjoint_from_prior_selected_patches=not bool(set(ids)&used))
   if rec['disjoint_from_prior_selected_patches']:used.update(ids)
   rows.append(rec)
   np.savez_compressed(OUT/f'base-{n["node"]}-panel-{pi}-trial.npz',positions_mm=xyz,triangles=t,source_triangle_indices=ids)
 dart=next(n for n in r['nodes']if n['asset']=='arena-static');g=load_nodes(Path(dart['source']))[2][354];outline=[]
 for pi in [6,7]:
  xyz=loop(g[dart['patches'][pi]['triangle_indices']]);j=np.argmax(np.linalg.norm(xyz-xyz[0],axis=1))
  outline.append(dict(patch_index=pi,original_vertices=len(xyz),retained_boundary_vertices_by_rdp_tolerance_mm={str(tol):len(rdp(xyz[:j+1],tol))+len(rdp(np.concatenate([xyz[j:],xyz[:1]]),tol))-2 for tol in [.5,1,2,3]}))
 result=dict(panels=rows,hypothetical_disjoint_placed_savings=sum(x['hypothetical_placed_savings']for x in rows if x['disjoint_from_prior_selected_patches']),status='Individual local trials only. Combined panel mesh/export, manifold integration, placement equivalence, contacts and moving poses not validated. Savings assume all accepted individually and use recorded placements.',dart_outline_sensitivity=outline)
 (OUT/'shortlist.json').write_text(json.dumps(result,indent=2)+'\n')
 for x in rows:print(x['node'],x['patch_index'],x['source_triangles'],x['trial_triangles'],'vertex',round(x['source_all_vertex_to_trial_max_mm'],3),'reverse',round(x['trial_area_sample_max_mm'],3),'disjoint',x['disjoint_from_prior_selected_patches'])
 print('potential placed',result['hypothetical_disjoint_placed_savings']);print(outline)
if __name__=='__main__':run()
