"""Collision-only local Outpost hardware boxes and slender Rune arm profiles."""
import copy,itertools,json
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import ConvexHull
from shapely.geometry import MultiPoint,Polygon
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles,orient_polygons
from inventory import ROOT,OUT,STAGE,BINDINGS,hub
from gltf_scene import read_glb,write_glb,scene_nodes,accessor
from simplify_package import compact,append_accessor,scene_triangles

def islands(g):
 v,inv=np.unique(np.round(g.reshape(-1,3),3),axis=0,return_inverse=True);f=inv.reshape(-1,3);e=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);_,labels=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(v),len(v))),directed=False)
 return [np.flatnonzero(labels[f[:,0]]==i)for i in np.unique(labels)]
def extrude_profile(profile,lo,hi,axes,center):
 profile=orient_polygons(profile);geos=[]
 for tri in constrained_delaunay_triangles(profile).geoms:
  xy=np.array(tri.exterior.coords)[:3]
  area=(xy[1,0]-xy[0,0])*(xy[2,1]-xy[0,1])-(xy[1,1]-xy[0,1])*(xy[2,0]-xy[0,0])
  if area<0:xy=xy[::-1]
  geos.extend([np.column_stack([xy[::-1],np.full(3,lo)]),np.column_stack([xy,np.full(3,hi)])])
 polys=list(profile.geoms)if profile.geom_type=='MultiPolygon'else[profile]
 for poly in polys:
  for ring in [poly.exterior,*poly.interiors]:
   pts=np.array(ring.coords)
   for a,b in zip(pts[:-1],pts[1:]):
    aa=np.r_[a,lo];bb=np.r_[b,lo];at=np.r_[a,hi];bt=np.r_[b,hi];geos.extend([np.array([aa,bb,bt]),np.array([aa,bt,at])])
 return np.array(geos)@axes+center

def build(asset):
 stage=json.loads(STAGE.read_text());source=Path(stage['collision_assets'][asset]['path']);d,c,n=hub.scan.load_nodes(source);_,blob=read_glb(source);a=copy.deepcopy(d);binary=bytearray(blob);world={i:w for i,w,parent in scene_nodes(d)};records=[];rejections=[]
 for node,g in n.items():
  pieces=[];selected=np.zeros(len(g),bool)
  if asset=='outpost':
   # Only the three dense fixed hardware owners. Leave all rotor/armor owners exact.
   if node not in [14,23,25]:continue
   for island,ids in enumerate(islands(g)):
    if len(ids)<25:continue
    pts=np.unique(g[ids].reshape(-1,3),axis=0);center=pts.mean(0);_,_,axes=np.linalg.svd(pts-center,full_matrices=False);q=(pts-center)@axes.T;lo=q.min(0)-.1;hi=q.max(0)+.1
    if np.linalg.norm(hi-lo)>35 or min(hi-lo)<.2:continue
    vertices=np.array(list(itertools.product(*zip(lo,hi))))@axes+center
    pieces.append(dict(kind='local-hardware-box',island=island,source_triangle_indices=ids.tolist(),vertices_world_mm=vertices.tolist()));selected[ids]=True
  else:
   if not c[node]or '/arm-'not in c[node]or len(g)<500:continue
   pts=np.unique(g.reshape(-1,3),axis=0);center=pts.mean(0);_,_,axes=np.linalg.svd(pts-center,full_matrices=False);q=(pts-center)@axes.T;ext=np.ptp(q,axis=0)
   if ext[2]>8 or ext[0]/ext[1]<3:continue
   polygon=MultiPoint(q[:,:2]).convex_hull.simplify(.5,preserve_topology=True).buffer(.65,join_style=2).convex_hull
   # Preserve the convex outline while removing bores and narrow scallops.
   polygon=polygon.union(MultiPoint(q[:,:2]).convex_hull).convex_hull
   # Keep large slots as real holes; only small bores are filled.
   projected=(g-center)@axes.T
   raw=unary_union([Polygon(t[:,:2])for t in projected if Polygon(t[:,:2]).area>1e-8])
   polys=list(raw.geoms)if raw.geom_type=='MultiPolygon'else[raw];holes=[]
   for poly in polys:
    for ring in poly.interiors:
     hole=Polygon(ring)
     if hole.area>100:
      hole=hole.simplify(.4,preserve_topology=True).buffer(-.65)
      if not hole.is_empty:holes.append(hole)
   def clean(poly):return Polygon(poly.exterior,[ring.coords for ring in poly.interiors if Polygon(ring).area>100])
   filled=unary_union([clean(poly)for poly in polys])
   profile=filled.simplify(.6,preserve_topology=True).buffer(.7,join_style=2,mitre_limit=2)
   if raw.difference(profile).area>1e-4:rejections.append(dict(node=node,reason='source projection lost'));continue
   geo=extrude_profile(profile,q[:,2].min()-.1,q[:,2].max()+.1,axes,center)
   reverse=hub.p.distances(hub.p.probes(geo,5000),g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3));error=float(reverse.max())
   if error>4 or len(geo)>=len(g):rejections.append(dict(node=node,source_triangles=len(g),trial_triangles=len(geo),sampled_reverse_max_mm=error));continue
   pieces.append(dict(kind='slender-arm-profile',source_triangle_indices=list(range(len(g))),triangle_geometry_world_mm=geo.tolist(),profile_wkt=profile.wkt,source_frame_center_mm=center.tolist(),source_frame_axes=axes.tolist(),thickness_bounds_mm=[float(q[:,2].min()-.1),float(q[:,2].max()+.1)],preserved_large_slots=len(holes),pca_extents_mm=ext.tolist(),sampled_reverse_max_mm=error));selected[:]=True
  if not pieces:continue
  mesh=copy.deepcopy(d['meshes'][d['nodes'][node]['mesh']]);primitives=[];selectors=[];offset=0
  for pi,p in enumerate(mesh['primitives']):
   idx=accessor(d,blob,p['indices']).reshape(-1,3);mask=selected[offset:offset+len(idx)];offset+=len(idx)
   if (~mask).any():
    pr=copy.deepcopy(p);pr['indices']=append_accessor(a,binary,idx[~mask].astype(np.uint32).ravel(),'SCALAR',5125);primitives.append(pr)
   selectors.append(dict(source_primitive=pi,source_triangles=len(idx),selected_triangle_indices=np.flatnonzero(mask).tolist(),retained_triangles=int((~mask).sum())))
  inv=np.linalg.inv(world[node]);proxy=[]
  for piece in pieces:
   if 'vertices_world_mm'in piece:
    verts=np.array(piece['vertices_world_mm']);local=verts@inv[:3,:3].T+inv[:3,3]*1000;local=(local*.001).astype(np.float32).astype(float)*1000
    piece['vertices_local_mm']=local.tolist();geo=hub.v.hull_geometry(local)
   else:
    geo=np.array(piece.pop('triangle_geometry_world_mm'));geo=geo@inv[:3,:3].T+inv[:3,3]*1000;geo=(geo*.001).astype(np.float32).astype(float)*1000
   piece['proxy_triangles']=len(geo);proxy.append(geo)
  proxy=np.concatenate(proxy);primitives.append(hub.p.pair.primitive(a,binary,proxy,mesh['primitives'][0]));mesh['primitives']=primitives;a['nodes'][node]['mesh']=len(a['meshes']);a['meshes'].append(mesh)
  records.append(dict(node=node,name=d['nodes'][node]['name'],component=c[node],source_triangles=len(g),selected_triangles=int(selected.sum()),retained_triangles=int((~selected).sum()),proxy_triangles=len(proxy),pieces=pieces,selectors=selectors,world_matrix=world[node].tolist()))
  print(asset,node,int(selected.sum()),'->',len(proxy),'triangles',flush=True)
 target=OUT/f'{asset}-collision.glb';write_glb(target,a,compact(a,binary));td,_=read_glb(target);saving=scene_triangles(d)-scene_triangles(td);exact=hub.p.pair.unchanged(source,target,{x['node']for x in records});placements=stage['collision_assets'][asset]['placements']
 report=dict(asset=asset,source_collision=str(source),source_sha256=hub.scan.digest(source),candidate_collision=str(target),candidate_sha256=hub.scan.digest(target),source_triangles=scene_triangles(d),candidate_triangles=scene_triangles(td),triangles_saved=saving,placements=placements,placed_triangles_saved=saving*placements,records=records,rejections=rejections,unchanged_other_mesh_owners_exact=exact,unchanged_visual=stage['visual_assets'][asset],input_pins={str(p):hub.scan.digest(p)for p in [STAGE,BINDINGS,source,Path(stage['visual_assets'][asset]['path'])]},installed=False)
 (OUT/f'{asset}-verification.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 reports=[build(asset)for asset in ['outpost','rune']]
 print('Placed triangle savings:',[(r['asset'],r['placed_triangles_saved'])for r in reports])
