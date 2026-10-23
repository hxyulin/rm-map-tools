"""Five short spoke hulls and a filled multi-section center per fixed Rune hub."""
import copy,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull,HalfspaceIntersection
from scipy.optimize import linprog
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-rune-hub-coarse'))
import coarse
hub=coarse.hub;p=coarse.p;v=coarse.v;scan=coarse.scan
from gltf_scene import read_glb,write_glb,scene_nodes
from simplify_package import compact,scene_triangles
OUT=ROOT/'out/rmuc2027-rune-hub-spokes'
BASE=coarse.BASE;STAGE=coarse.STAGE;BINDINGS=coarse.BINDINGS

def hull_shape(points,tolerance=1.):
 points=np.unique(points,axis=0);points=points[ConvexHull(points).vertices];selected,_,recession=v.compact_hull(points,tolerance=tolerance);selected=selected[ConvexHull(selected).vertices];center=selected.mean(0)
 return dict(kind='convex_hull',vertices_local_m=((selected-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1])),recession

def clipped_points(points,axis_cut,positive):
 h=ConvexHull(points);plane=np.array([0.,0.,1. if positive else-1.,-axis_cut if positive else axis_cut]);half=np.vstack([h.equations,plane]);norm=np.linalg.norm(half[:,:3],axis=1);half=half/norm[:,None]
 res=linprog([0,0,0,-1],A_ub=np.column_stack([half[:,:3],np.ones(len(half))]),b_ub=-half[:,3],bounds=[(None,None)]*3+[(0,None)],method='highs');assert res.success and res.x[3]>1e-6
 return HalfspaceIntersection(half,res.x[:3]).intersections

def main():
 OUT.mkdir(exist_ok=True);base=json.loads(BASE.read_text());stage=json.loads(STAGE.read_text());source=Path(base['source_collision']);d,c,n=scan.load_nodes(source);bindings=json.loads(BINDINGS.read_text());parents={i:parent for i,w,parent in scene_nodes(d)}
 parts=[];replacements={};omitted=set();definitions=[];groups=[]
 for bi,motion in enumerate(bindings['rune_motion']):
  bank='bank-a'if bi==0 else'bank-b';disk=272 if bi==0 else 426;owner=274 if bi==0 else 428;root=9 if bi==0 else 16
  axis=np.array(motion['axis']);a,u,w=p.basis(axis);frame=np.column_stack([u,w,a]);pivot=np.array(motion['pivot_m'])*1000;ids={i for i in n if c[i]==f'rune/banks/{bank}/hub-cluster'}
  arms=np.concatenate([g.reshape(-1,3)for i,g in n.items()if c[i].startswith(f'rune/banks/{bank}/arm-')]);arm=(arms-pivot)@frame;cut=float(arm[:,2].min()-5 if bi==0 else arm[:,2].max()+5)
  points=np.unique(n[owner].reshape(-1,3),axis=0);q=(points-pivot)@frame;rad=np.linalg.norm(q[:,:2],axis=1);theta=np.arctan2(q[:,1],q[:,0]);weights=(rad/rad.max())**12;phase=float(np.angle(np.sum(weights*np.exp(theta*5j)))/5);spoke_shapes=[];spoke_def=[]
  for k in range(5):
   angle=phase+k*2*np.pi/5;delta=np.angle(np.exp((theta-angle)*1j));selected=q[(abs(delta)<=np.pi/5)&(rad>=110.)];clipped=clipped_points(selected,cut,bi==0);shape,error=hull_shape(clipped@frame.T+pivot,tolerance=2.)
   spoke_shapes.append(shape);spoke_def.append(dict(spoke=k,angle_deg=float(np.rad2deg(angle)),source_sector_points=len(selected),clipped_outer_vertex_recession_max_mm=error,hull_vertices=len(shape['vertices_local_m'])))
  # Three polygon rings form one convex center: rear collar, shoulder, front neck.
  rings=[(-176.,135.),(-125.,135.),(45.5,110.)]if bi==0 else[(-45.5,110.),(125.,135.),(176.,135.)]
  theta12=np.arange(12)*2*np.pi/12;center_points=np.concatenate([np.column_stack([radius*np.cos(theta12),radius*np.sin(theta12),np.full(12,z)])for z,radius in rings])@frame.T+pivot
  center_shape,_=hull_shape(center_points,tolerance=.001);selected={owner:spoke_shapes,disk:[center_shape]};extra=[]
  if bi==1:
   shape,error=hull_shape(n[429].reshape(-1,3),tolerance=.5);selected[429]=[shape];extra.append(dict(source_node=429,hull_vertices=len(shape['vertices_local_m']),outer_vertex_recession_max_mm=error))
  omitted|=ids-set(selected)
  groupid=f'{bank}-fixed-hub'
  for i,shapes in selected.items():
   replacements[i]=np.concatenate([v.geometry(s)for s in shapes])
   for k,shape in enumerate(shapes):parts.append(dict(id=f'{groupid}-{i}-{k}',component_id=c[i],source_node_index=root,source_node_name=d['nodes'][root]['name'],source_group=groupid,diagnostic_carrier_node=i,shape=shape))
  groups.append(dict(id=groupid,component_root_node=root,covered_source_mesh_nodes=sorted(ids),rigid_owner_requirement='All covered leaves must remain fixed together; reject future per-leaf motion or selectors requiring omitted meshes.'))
  definitions.append(dict(bank=bank,frame_columns=frame.tolist(),pivot_mm=pivot.tolist(),source_hub_nodes=sorted(ids),spoke_source_node=owner,spoke_phase_deg=float(np.rad2deg(phase)),spoke_inner_source_radius_mm=110.,spoke_axial_clip_mm=cut,spokes=spoke_def,center_polygon_sides=12,center_rings_axial_radius_mm=rings,center_solid=True,extra_reverse_bracket=extra))
 selected=set(replacements)|omitted;tmp=OUT/'replaced.glb';hub.replace(source,tmp,replacements);td,tb=read_glb(tmp)
 for i in omitted:del td['nodes'][i]['mesh']
 target=OUT/'rune-collision.glb';write_glb(target,td,compact(td,tb));exact=p.pair.unchanged(source,target,selected);td,_=read_glb(target)
 rd=copy.deepcopy(d);_,blob=read_glb(source)
 for i in selected:del rd['nodes'][i]['mesh']
 folder=OUT/'native-review';folder.mkdir(exist_ok=True);write_glb(folder/'remainder.glb',rd,compact(rd,blob));rd,_=read_glb(folder/'remainder.glb');p.pair.unchanged(source,folder/'remainder.glb',selected)
 recipe=dict(schema='rm-map-tools.native-component-envelope-review-1',units='m',coordinate_frame='source_glb_active_scene',quaternion_order='xyzw',source=dict(file=str(source),sha256=scan.digest(source)),retained_mesh=dict(file='remainder.glb',sha256=scan.digest(folder/'remainder.glb'),triangles=scene_triangles(rd)),replaced_node_indices=sorted(selected),source_groups=groups,native_parts=parts,deliberately_omitted_nodes=sorted(omitted),runtime_supported=False,installed=False)
 (folder/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n');count=scene_triangles(td);ns=copy.deepcopy(stage);ns['collision_assets']['rune']=dict(path=str(target),sha256=scan.digest(target),triangles=count,placements=1,placed_triangles=count);ns['placed_collision_triangles']=sum(x['placed_triangles']for x in ns['collision_assets'].values());ns.update(variant='rune-hub-spokes',installed=False,contact_validated=False);(OUT/'paired-stage.json').write_text(json.dumps(ns,indent=2)+'\n')
 removed=sum(len(n[i])for i in selected);before=json.loads(hub.BASE.read_text());report=dict(source_collision=str(source),source_sha256=scan.digest(source),candidate_collision=str(target),candidate_sha256=scan.digest(target),selected_nodes=sorted(selected),omitted_nodes=sorted(omitted),definitions=definitions,native_review=str(folder/'recipe.json'),native_hulls=len(parts),source_hub_triangles=removed,native_rune_remaining_mesh_triangles=scene_triangles(rd),diagnostic_rune_triangles=count,field_native_mesh_triangles=before['field_native_mesh_triangles']-removed,field_native_shape_counts={**before['field_native_shape_counts'],'convex_hull':before['field_native_shape_counts']['convex_hull']+len(parts)},field_preview_triangles=ns['placed_collision_triangles'],unchanged_owners_exact=exact,unchanged_visual=base['unchanged_visual'],unchanged_visual_sha256=base['unchanged_visual_sha256'],input_pins={str(path):scan.digest(path)for path in [BASE,STAGE,BINDINGS,source,Path(base['unchanged_visual'])]},runtime_supported=False,installed=False,contact_validated=False)
 (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print('Hub mesh',removed,'to',len(parts),'hulls; Rune remainder',scene_triangles(rd),'diagnostic',count,flush=True)
if __name__=='__main__':main()
