"""Complete source-triangle containment, prior-volume containment and ray checks."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from cover import OUT,PREVIOUS,spokes,p,v,scan,read_glb,scene_triangles

def world_vertices(s):return np.array(s['vertices_local_m'])*1000+np.array(s['pose']['translation_m'])*1000

def planes(vertices):return ConvexHull(vertices).equations

def ray_entry(origin,direction,equations,length=2000.):
 lo=0.;hi=length
 for eq in equations:
  a=float(eq[:3]@direction);b=float(eq[:3]@origin+eq[3])
  if abs(a)<1e-12:
   if b>0:return None
  elif a<0:lo=max(lo,-b/a)
  else:hi=min(hi,-b/a)
  if lo>hi:return None
 return lo if hi>=0 and lo<=length else None

def main():
 r=json.loads((OUT/'verification.json').read_text());d,c,n=scan.load_nodes(Path(r['source_collision']));a,ac,new=scan.load_nodes(Path(r['candidate_collision']));recipe=json.loads(Path(r['native_review']).read_text());assignment=json.loads(Path(r['coverage_assignments']).read_text());previous=json.loads(PREVIOUS.read_text());oldrecipe=json.loads(Path(previous['native_review']).read_text());allparts=recipe['native_parts'];assert len(allparts)==13
 for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
 assert scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']and scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
 selected=set(r['selected_nodes']);p.pair.unchanged(Path(r['source_collision']),Path(r['candidate_collision']),selected)
 arms=[i for i in n if '/arm-'in c[i]]
 for i in arms:assert np.array_equal(n[i],new[i])
 names=[x.get('name')for x in a['nodes']];bindings=json.loads(spokes.BINDINGS.read_text());moving=[name for m in bindings['rune_motion']for name in m['bodies']]
 for name in moving:assert names.count(name)==1
 source_count=0;native_margin=np.inf;diagnostic_margin=np.inf;old_margin=np.inf;join=[];native_eq={};diag_eq={}
 for definition in r['definitions']:
  bank=definition['bank'];group=bank+'-fixed-hub';parts=[x for x in allparts if x['source_group']==group];eqs=[planes(world_vertices(x['shape']))for x in parts];native_eq[bank]=eqs;offsets={};deqs=[]
  for part in parts:
   carrier=part['diagnostic_carrier_node'];start=offsets.get(carrier,0);count=len(v.geometry(part['shape']));g=new[carrier][start:start+count];assert len(g)==count
   _,indices=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);tri=indices.reshape(-1,3);edges=np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1);_,uses=np.unique(edges,axis=0,return_counts=True);assert (uses==2).all()
   deqs.append(planes(g.reshape(-1,3)));offsets[carrier]=start+count
  diag_eq[bank]=deqs
  for node,labels in assignment[bank].items():
   triangles=n[int(node)];labels=np.array(labels);assert len(labels)==len(triangles);source_count+=len(triangles)
   for k in range(len(parts)):
    points=triangles[labels==k].reshape(-1,3)
    if not len(points):continue
    native=-np.max(points@eqs[k][:,:3].T+eqs[k][:,3]);diag=-np.max(points@deqs[k][:,:3].T+deqs[k][:,3]);native_margin=min(native_margin,float(native));diagnostic_margin=min(diagnostic_margin,float(diag));assert native>.20 and diag>.19
  # A convex set containing all vertices of a prior hull contains that whole hull.
  oldparts=[x for x in oldrecipe['native_parts']if x['source_group']==group]
  for k,oldpart in enumerate(oldparts):
   pts=world_vertices(oldpart['shape']);margin=-np.max(pts@eqs[k][:,:3].T+eqs[k][:,3]);old_margin=min(old_margin,float(margin));assert margin>.20
  # Each spoke shares a strictly interior witness with the center: no butt seam.
  source_points=np.concatenate([n[int(i)].reshape(-1,3)for i in assignment[bank]])
  for k in range(5):
   m1=-(source_points@eqs[k][:,:3].T+eqs[k][:,3]).max(1);m2=-(source_points@eqs[5][:,:3].T+eqs[5][:,3]).max(1);best=float(np.minimum(m1,m2).max());assert best>.1;join.append(dict(bank=bank,spoke=k,shared_interior_ball_radius_lower_bound_mm=best))
 assert source_count==r['source_hub_triangles']
 rd,_=read_glb(Path(r['native_review']).parent/'remainder.glb');assert scene_triangles(rd)==r['native_rune_remaining_mesh_triangles']
 # Finite directional regression rays through all source centroids and vertices.
 raychecks=[]
 for definition in r['definitions']:
  bank=definition['bank'];frame=np.array(definition['frame_columns']);ids=definition['source_hub_nodes'];geometry=np.concatenate([n[i]for i in ids]);pts=np.concatenate([np.unique(geometry.reshape(-1,3),axis=0),geometry.mean(1)])
  missed=0;total=0
  for localdir in [[0,0,1],[0,0,-1],[1,0,0],[0,1,0],[1,.4,.7],[-.6,1,.5]]:
   direction=np.array(localdir,float)@frame.T;direction/=np.linalg.norm(direction)
   origins=pts-direction*1000;hits=np.zeros(len(pts),bool)
   for eq in native_eq[bank]:
    aa=eq[:,:3]@direction;bb=origins@eq[:,:3].T+eq[:,3];parallel=abs(aa)<1e-12;valid=~(bb[:,parallel]>0).any(1);negative=aa < -1e-12;positive=aa > 1e-12
    lo=np.maximum(0,np.max(-bb[:,negative]/aa[negative],axis=1,initial=0));hi=np.minimum(2000,np.min(-bb[:,positive]/aa[positive],axis=1,initial=2000));hits|=valid&(lo<=hi)
   missed+=int((~hits).sum());total+=len(pts)
  assert missed==0;raychecks.append(dict(bank=bank,rays=total,misses=missed))
 stage=json.loads((OUT/'paired-stage.json').read_text())
 for role in ['visual','collision']:
  assert sum(x['placed_triangles']for x in stage[role+'_assets'].values())==stage['placed_'+role+'_triangles']
  for x in stage[role+'_assets'].values():assert scan.digest(Path(x['path']))==x['sha256']
 proof=dict(source_triangles_fully_enclosed=source_count,closed_reopened_preview_hulls=13,native_triangle_margin_min_mm=native_margin,reopened_glb_triangle_margin_min_mm=diagnostic_margin,previous_native_hulls_fully_enclosed=13,previous_hull_margin_min_mm=old_margin,spoke_center_overlap_witnesses=join,ray_checks=raychecks,moving_arm_payloads_exact=len(arms),moving_selectors_preserved=len(moving),visual_assets_exact=True,old_axial_clearance_claim_withdrawn=True,
 theorem='Each complete original triangle lies in one convex solid. Thus source surface coverage and collision with a swept ball of any radius are not lost by this replacement, in exact geometry. This does not alone prove runtime CCD/loader behavior.',runtime_supported=False,installed=False)
 (OUT/'geometry-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(triangles=source_count,native_margin_mm=native_margin,glb_margin_mm=diagnostic_margin,rays=raychecks)),flush=True)
if __name__=='__main__':main()
