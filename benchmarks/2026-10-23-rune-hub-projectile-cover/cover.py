"""Conservative spoke solids: every source triangle and prior hull is enclosed."""
import copy,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull,HalfspaceIntersection
from scipy.optimize import linprog
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-rune-hub-spokes'))
import spokes
p=spokes.p;v=spokes.v;scan=spokes.scan;hub=spokes.hub
from gltf_scene import read_glb,write_glb
from simplify_package import compact,scene_triangles
OUT=ROOT/'out/rmuc2027-rune-hub-projectile-cover'
PREVIOUS=spokes.OUT/'verification.json'
PADDING_MM=.25

def support_hull(points,frame):
 # Source outer-hull face directions preserve tapered tips while enclosing
 # every input point. Near-identical directions merge; all offsets are outward.
 local=points@frame;h=ConvexHull(local);tri=local[h.simplices];areas=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1);chosen=list(np.concatenate([np.eye(3),-np.eye(3)]))
 for index in np.argsort(-areas):
  normal=h.equations[index,:3]
  if max(float(normal@old)for old in chosen)<np.cos(np.deg2rad(5.)):chosen.append(normal)
 directions=np.array(chosen)
 supports=(local@directions.T).max(0)+PADDING_MM;half=np.column_stack([directions,-supports]);res=linprog([0,0,0,-1],A_ub=np.column_stack([directions,np.ones(len(directions))]),b_ub=supports,bounds=[(None,None)]*3+[(0,None)],method='highs');assert res.success
 vertices=HalfspaceIntersection(half,res.x[:3]).intersections@frame.T;vertices=np.unique(np.round(vertices,4),axis=0);vertices=vertices[ConvexHull(vertices).vertices];center=vertices.mean(0)
 shape=dict(kind='convex_hull',vertices_local_m=((vertices-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1]))
 return shape

def main():
 OUT.mkdir(exist_ok=True);previous=json.loads(PREVIOUS.read_text());source=Path(previous['source_collision']);d,c,n=scan.load_nodes(source);old_recipe=json.loads(Path(previous['native_review']).read_text());oldparts=old_recipe['native_parts'];parts=[];replacements={};groups=copy.deepcopy(old_recipe['source_groups']);assignments={};definitions=[]
 for bi,definition in enumerate(previous['definitions']):
  bank=definition['bank'];group=bank+'-fixed-hub';owner=definition['spoke_source_node'];disk=272 if bi==0 else 426;root=9 if bi==0 else 16;frame=np.array(definition['frame_columns']);pivot=np.array(definition['pivot_mm']);phase=np.deg2rad(definition['spoke_phase_deg']);ids=definition['source_hub_nodes']
  buckets=[[]for k in range(5)];center_triangles=[];assigned_by_node={};extra_triangles=[]
  for i in ids:
   g=n[i];local=(g-pivot)@frame;radius=np.linalg.norm(local[:,:,:2],axis=2);labels=np.full(len(g),-1,dtype=int)
   if i==429:extra_triangles.extend(g);labels[:]=6
   else:
    central=(radius<=135.).all(1);center_triangles.extend(g[central]);labels[central]=5
    centroid=local.mean(1);theta=np.arctan2(centroid[:,1],centroid[:,0]);sector=np.floor(((theta-phase+np.pi/5)%(2*np.pi))/(2*np.pi/5)).astype(int)
    for k in range(5):mask=(~central)&(sector==k);buckets[k].extend(g[mask]);labels[mask]=k
   assert (labels>=0).all();assigned_by_node[str(i)]=labels.tolist()
  shapes=[]
  for k,triangles in enumerate(buckets):
   old=next(x for x in oldparts if x['source_group']==group and x['diagnostic_carrier_node']==owner and x['id'].endswith('-'+str(k)));oldverts=np.array(old['shape']['vertices_local_m'])*1000+np.array(old['shape']['pose']['translation_m'])*1000
   angle=phase+k*2*np.pi/5;radial=np.array([np.cos(angle),np.sin(angle),0]);tangent=np.array([-np.sin(angle),np.cos(angle),0]);oriented=frame@np.column_stack([radial,tangent,[0,0,1]])
   points=np.concatenate([np.array(triangles).reshape(-1,3),oldverts]);shapes.append(support_hull(points,oriented))
  oldcenter=next(x for x in oldparts if x['source_group']==group and x['diagnostic_carrier_node']==disk)['shape'];oldvertices=np.array(oldcenter['vertices_local_m'])*1000+np.array(oldcenter['pose']['translation_m'])*1000
  central_points=np.concatenate([np.array(center_triangles).reshape(-1,3),oldvertices]);local=(central_points-pivot)@frame;radius=max(135.,float(np.linalg.norm(local[:,:2],axis=1).max()));outer=(radius+.5)/np.cos(np.pi/12);theta=np.arange(12)*2*np.pi/12
  cp=np.concatenate([np.column_stack([outer*np.cos(theta),outer*np.sin(theta),np.full(12,z)])for z in [local[:,2].min()-.5,local[:,2].max()+.5]])@frame.T+pivot
  center=cp.mean(0);shapes.append(dict(kind='convex_hull',vertices_local_m=((cp-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1])))
  if extra_triangles:
   oldextra=next(x for x in oldparts if x['diagnostic_carrier_node']==429)['shape'];points=np.concatenate([np.array(extra_triangles).reshape(-1,3),np.array(oldextra['vertices_local_m'])*1000+np.array(oldextra['pose']['translation_m'])*1000]);shapes.append(support_hull(points,frame))
  replacements[owner]=np.concatenate([v.geometry(s)for s in shapes[:5]]);replacements[disk]=v.geometry(shapes[5])
  if extra_triangles:replacements[429]=v.geometry(shapes[6])
  for index,shape in enumerate(shapes):parts.append(dict(id=f'{group}-cover-{index}',component_id=f'rune/banks/{bank}/hub-cluster',source_node_index=root,source_node_name=d['nodes'][root]['name'],source_group=group,local_piece_index=index,diagnostic_carrier_node=owner if index<5 else disk if index==5 else 429,shape=shape))
  assignments[bank]=assigned_by_node;definitions.append(dict(bank=bank,frame_columns=frame.tolist(),pivot_mm=pivot.tolist(),spoke_phase_deg=float(np.rad2deg(phase)),spoke_support_planes='source convex outer face directions plus bounding axes',padding_mm=PADDING_MM,source_hub_nodes=ids,center_sides=12,center_circumradius_mm=outer,center_axial_mm=[float(local[:,2].min()-.5),float(local[:,2].max()+.5)],source_triangles_per_piece=[len(x)for x in buckets]+[len(center_triangles)]+([len(extra_triangles)]if extra_triangles else[]),axial_trimming=False))
 selected=set(previous['selected_nodes']);omitted=selected-set(replacements);temporary=OUT/'replaced.glb';hub.replace(source,temporary,replacements);td,tb=read_glb(temporary)
 for i in omitted:del td['nodes'][i]['mesh']
 target=OUT/'rune-collision.glb';write_glb(target,td,compact(td,tb));p.pair.unchanged(source,target,selected);td,_=read_glb(target)
 folder=OUT/'native-review';folder.mkdir(exist_ok=True);oldrem=Path(previous['native_review']).parent/'remainder.glb';rd,rb=read_glb(oldrem);write_glb(folder/'remainder.glb',rd,rb)
 recipe=copy.deepcopy(old_recipe);recipe.update(native_parts=parts,retained_mesh=dict(file='remainder.glb',sha256=scan.digest(folder/'remainder.glb'),triangles=scene_triangles(rd)),coverage_policy='Each original hub triangle assigned wholly to one enclosing convex piece; all previous native hulls also enclosed. No source-receding simplification or axial trimming.',coverage_assignments_file='../triangle-assignments.json',installed=False)
 (OUT/'triangle-assignments.json').write_text(json.dumps(assignments)+'\n');(folder/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
 stage=json.loads((spokes.OUT/'paired-stage.json').read_text());count=scene_triangles(td);stage['collision_assets']['rune']=dict(path=str(target),sha256=scan.digest(target),triangles=count,placements=1,placed_triangles=count);stage['placed_collision_triangles']=sum(x['placed_triangles']for x in stage['collision_assets'].values());stage['variant']='rune-hub-projectile-cover';(OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
 report=copy.deepcopy(previous);report.update(candidate_collision=str(target),candidate_sha256=scan.digest(target),native_review=str(folder/'recipe.json'),definitions=definitions,diagnostic_rune_triangles=count,field_preview_triangles=stage['placed_collision_triangles'],coverage_assignments=str(OUT/'triangle-assignments.json'),axial_trimming=False,previous_rotation_clearance_claim_withdrawn=True)
 report['input_pins'][str(PREVIOUS)]=scan.digest(PREVIOUS);report['input_pins'][str(Path(previous['native_review']))]=scan.digest(Path(previous['native_review']));(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print('Built',len(parts),'enclosing hulls; diagnostic Rune',count,flush=True)
if __name__=='__main__':main()
