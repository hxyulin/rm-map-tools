"""Fit Dart top rungs, lower rails and deck separately, keeping slim sides exact."""
import copy,json,itertools
from pathlib import Path
import numpy as np
from shapely.geometry import MultiPoint
from scipy.spatial import ConvexHull
from inventory import ROOT,OUT,STAGE,hub,local_geometry,islands
from gltf_scene import read_glb,write_glb,scene_nodes,accessor
from simplify_package import compact,scene_triangles,append_accessor

def fit_x_prism(triangles,padding=.25):
 region=MultiPoint(triangles[:,:,1:].reshape(-1,2)).minimum_rotated_rectangle.buffer(padding,join_style=2)
 xy=np.array(region.exterior.coords)[:-1]
 return np.concatenate([np.column_stack([np.full(len(xy),x),xy])for x in [triangles[:,:,0].min()-padding,triangles[:,:,0].max()+padding]])
def covered_by(g,vertices):
 eq=ConvexHull(vertices).equations
 return (g.reshape(-1,3)@eq[:,:3].T+eq[:,3]).reshape(len(g),3,-1).max((1,2))<1e-4

def main():
 stage=json.loads(STAGE.read_text());source=Path(stage['collision_assets']['arena-static']['path']);assert hub.scan.digest(source)==stage['collision_assets']['arena-static']['sha256'];d,b=read_glb(source);a=copy.deepcopy(d);binary=bytearray(b);records=[];world={i:w for i,w,parent in scene_nodes(d)}
 for node in [354,587]:
  groups=local_geometry(d,b,node);g=np.concatenate(groups[:-1]);spans=np.ptp(g,axis=1);centers=g.mean(1);pieces=[];selected=np.zeros(len(g),bool)
  for i,z in enumerate([-314.,-77.,313.,492.]):
   mask=(spans[:,0]>500)&(g[:,:,1].max(1)<-1000)&(abs(centers[:,2]-z)<35)&(spans[:,2]<45)
   assert mask.any();pieces.append(dict(kind='top-rung',label=f'top-{i}',vertices_mm=fit_x_prism(g[mask]).tolist()))
  for i,z in enumerate([-810.,-370.,135.,610.,810.]):
   mask=(spans[:,0]>500)&(g[:,:,1].min(1)>(-7 if i==4 else -3))&(g[:,:,1].max(1)<31)&(abs(centers[:,2]-z)<22)&(spans[:,2]<35)
   assert mask.any();pieces.append(dict(kind='base-crossbar',label=f'base-{i}',vertices_mm=fit_x_prism(g[mask]).tolist()))
  # Broad deck faces define the exact original top plane; avoid global fitting bounds.
  mask=(g[:,:,1].min(1)>=-55.001)&(g[:,:,1].max(1)<=-51.999)&(abs(g[:,:,0]).max(1)<285)&(spans[:,2]>800)
  assert mask.any();p=g[mask].reshape(-1,3);lo=p.min(0);hi=p.max(0);vertices=np.array(list(itertools.product(*zip(lo,hi))));pieces.append(dict(kind='deck-slab',label='deck',vertices_mm=vertices.tolist()))
  for p in pieces:
   p['vertices_mm']=(np.array(p['vertices_mm'])*.001).astype(np.float32).astype(float).tolist()
   p['vertices_mm']=(np.array(p['vertices_mm'])*1000).tolist()
   selected|=covered_by(g,np.array(p['vertices_mm']))
  # Local hardware is kept local rather than widening the whole rung/deck.
  remaining_ids=np.flatnonzero(~selected)
  for k,local_ids in enumerate(islands(g[remaining_ids])):
   ids=remaining_ids[local_ids]
   if len(ids)<=12:continue
   pts=g[ids].reshape(-1,3);lo=pts.min(0);hi=pts.max(0)
   if np.linalg.norm(hi-lo)>150 or min(hi-lo)<.1:continue
   vertices=np.array(list(itertools.product(*zip(lo-.05,hi+.05))))
   vertices=(vertices*.001).astype(np.float32).astype(float)*1000
   pieces.append(dict(kind='local-fitting',label=f'fitting-{k}',vertices_mm=vertices.tolist()));selected[ids]=True
  # Keep the accepted side primitive byte-exact; filter only earlier original primitives.
  mesh=copy.deepcopy(d['meshes'][d['nodes'][node]['mesh']]);primitives=[];selectors=[];offset=0
  for index,(p,geo)in enumerate(zip(mesh['primitives'][:-1],groups[:-1])):
   mask=selected[offset:offset+len(geo)];offset+=len(geo);indices=accessor(d,b,p['indices']).reshape(-1,3)
   if (~mask).any():
    q=copy.deepcopy(p);q['indices']=append_accessor(a,binary,indices[~mask].astype(np.uint32).ravel(),'SCALAR',5125);primitives.append(q)
   selectors.append(dict(source_primitive=index,source_triangles=len(geo),selected_triangle_indices=np.flatnonzero(mask).tolist(),retained_triangles=int((~mask).sum())))
  primitives.append(copy.deepcopy(mesh['primitives'][-1]));proxy=np.concatenate([hub.v.hull_geometry(np.array(p['vertices_mm']))for p in pieces]);primitives.append(hub.p.pair.primitive(a,binary,proxy,mesh['primitives'][0]));mesh['primitives']=primitives;a['nodes'][node]['mesh']=len(a['meshes']);a['meshes'].append(mesh)
  records.append(dict(node=node,source_triangles=sum(map(len,groups)),selected_triangles=int(selected.sum()),retained_original_triangles=int((~selected).sum()),retained_side_triangles=len(groups[-1]),proxy_triangles=len(proxy),pieces=pieces,selectors=selectors,world_matrix=world[node].tolist()))
 target=OUT/'arena-static-collision.glb';write_glb(target,a,compact(a,binary));td,_=read_glb(target);exact=hub.p.pair.unchanged(source,target,{354,587});saving=scene_triangles(d)-scene_triangles(td);baseline=json.loads((ROOT/'out/rmuc2027-dart-beams-refined/verification.json').read_text());stage['collision_assets']['arena-static']=dict(path=str(target),sha256=hub.scan.digest(target),triangles=scene_triangles(td),placements=1,placed_triangles=scene_triangles(td));stage['placed_collision_triangles']-=saving;stage['variant']='dart-top-base-trial';(OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
 report=dict(source_collision=str(source),source_sha256=hub.scan.digest(source),candidate_collision=str(target),candidate_sha256=hub.scan.digest(target),records=records,placed_triangles_saved=saving,source_arena_triangles=scene_triangles(d),candidate_arena_triangles=scene_triangles(td),field_native_remaining_mesh_triangles=baseline['field_native_remaining_mesh_triangles']-saving,field_native_shape_counts=baseline['field_native_shape_counts'],unchanged_mesh_owners_exact=exact,input_pins={str(p):hub.scan.digest(p)for p in [source,STAGE]},installed=False)
 (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print('Top/base saves',saving,'placed triangles; arena',scene_triangles(td))
 for row in records:print(row['node'],row['selected_triangles'],'->',row['proxy_triangles'],'triangles;',len(row['pieces']),'boxes;',row['retained_original_triangles'],'original faces retained')
if __name__=='__main__':main()
