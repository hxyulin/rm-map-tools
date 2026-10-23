"""Replace only Dart side-frame triangles with closed conservative profile solids."""
import copy,hashlib,json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,LineString,Point
from shapely.strtree import STRtree
from shapely.ops import unary_union
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"benchmarks/2026-10-23-dart-side-profiles"))
from study import STAGE,hub,split_profile
OUT=ROOT/"out/rmuc2027-dart-simple-beams"
from gltf_scene import read_glb,write_glb,accessor,scene_nodes
from simplify_package import compact,scene_triangles,append_accessor

def projected(g):
 xy=g[:,1:];poly=Polygon(xy)
 if poly.area>1e-8:return poly
 pts=np.unique(xy,axis=0)
 return Point(pts[0])if len(pts)==1 else LineString(pts)

def local_geometry(d,b,node):
 mesh=d['meshes'][d['nodes'][node]['mesh']];arrays=[]
 for primitive in mesh['primitives']:
  points=accessor(d,b,primitive['attributes']['POSITION']).astype(float)*1000;indices=accessor(d,b,primitive['indices']).reshape(-1,3);arrays.append(points[indices])
 return arrays

def main():
 OUT.mkdir(exist_ok=True);stage=json.loads(STAGE.read_text());source=Path(stage['collision_assets']['arena-static']['path']);assert hub.scan.digest(source)==stage['collision_assets']['arena-static']['sha256'];d,blob=read_glb(source);a=copy.deepcopy(d);binary=bytearray(blob);records=[];worlds={i:w for i,w,parent in scene_nodes(d)}
 for node in [354,587]:
  groups=local_geometry(d,blob,node);g=np.concatenate(groups);allselected=np.zeros(len(g),bool);volumes=[];definitions=[]
  for sign in [-1,1]:
   mask,selected,raw,filled=split_profile(g,sign);allselected|=mask
   # Six primary beams and one thin longitudinal fitting/cable cover.
   endpoints=[((-1540,-400),(-20,-805)),((-1540,-400),(-1240,475)),((-1240,475),(10,800)),((15,-825),(15,825)),((-1240,475),(-20,-300)),((-1470,-348),(-20,-348)),((-143,-330),(-143,735))]
   segments=[LineString(pair) for pair in endpoints]
   centers=selected[:,:,1:].mean(1)
   assignment=np.array([[max(line.distance(Point(pt)) for pt in tri[:,1:])for line in segments]for tri in selected]).argmin(1)
   sidevol=[]
   for member in range(len(segments)):
    contributors=selected[assignment==member]
    if not len(contributors):continue
    # Fit one convex polygon to the full beam, including its assigned connectors.
    from shapely.geometry import MultiPoint
    region=MultiPoint(contributors[:,:,1:].reshape(-1,2)).minimum_rotated_rectangle.buffer(.5,join_style=2)
    xy=np.array(region.exterior.coords)[:-1];xy=(xy*.001).astype(np.float32).astype(float)*1000
    xy=xy[__import__('scipy').spatial.ConvexHull(xy).vertices]
    lo=float(np.float32((contributors[:,:,0].min()-.5)*.001))*1000
    hi=float(np.float32((contributors[:,:,0].max()+.5)*.001))*1000
    vertices=np.concatenate([np.column_stack([np.full(len(xy),x),xy])for x in [lo,hi]])
    geo=hub.v.hull_geometry(vertices);volumes.append(geo)
    sidevol.append(dict(member=member,x_bounds_mm=[lo,hi],profile_yz_mm=xy.tolist(),source_contributor_count=len(contributors),source_selected_indices=np.flatnonzero(assignment==member).tolist()))
   union=unary_union([Polygon(x['profile_yz_mm'])for x in sidevol])
   large=[]
   definitions.append(dict(side=sign,selected_triangles=int(mask.sum()),manual_beam_count=len(sidevol),convex_pieces=sidevol,large_opening_cores=large))
  mesh=copy.deepcopy(d['meshes'][d['nodes'][node]['mesh']]);primitives=[];selectors=[];offset=0
  for index,(primitive,geometry)in enumerate(zip(mesh['primitives'],groups)):
   mask=allselected[offset:offset+len(geometry)];offset+=len(geometry);oldindices=accessor(d,blob,primitive['indices']).reshape(-1,3)
   if (~mask).any():
    pr=copy.deepcopy(primitive);pr['indices']=append_accessor(a,binary,oldindices[~mask].astype(np.uint32).ravel(),'SCALAR',5125);primitives.append(pr)
   selectors.append(dict(source_primitive=index,source_triangles=len(geometry),selected_triangle_indices=np.flatnonzero(mask).tolist(),selected_sha256=hashlib.sha256(np.flatnonzero(mask).astype('<u8').tobytes()).hexdigest(),retained_triangles=int((~mask).sum())))
  proxy=np.concatenate(volumes);primitives.append(hub.p.pair.primitive(a,binary,proxy,mesh['primitives'][0]));mesh['primitives']=primitives;a['nodes'][node]['mesh']=len(a['meshes']);a['meshes'].append(mesh)
  records.append(dict(node=node,node_name=d['nodes'][node]['name'],component_id=d['nodes'][node].get('extras',{}),source_triangles=len(g),selected_triangles=int(allselected.sum()),retained_triangles=int((~allselected).sum()),proxy_triangles=len(proxy),convex_regions=len(volumes),selectors=selectors,definitions=definitions,world_matrix=worlds[node].tolist()))
 target=OUT/'arena-static-collision.glb';write_glb(target,a,compact(a,binary));exact=hub.p.pair.unchanged(source,target,{354,587});td,_=read_glb(target);saving=scene_triangles(d)-scene_triangles(td);before=json.loads((ROOT/'out/rmuc2027-rune-hub-projectile-cover/verification.json').read_text());stage['collision_assets']['arena-static']=dict(path=str(target),sha256=hub.scan.digest(target),triangles=scene_triangles(td),placements=1,placed_triangles=scene_triangles(td));stage['placed_collision_triangles']=sum(x['placed_triangles']for x in stage['collision_assets'].values());stage.update(variant='dart-side-profile-trial',installed=False,contact_validated=False);(OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
 report=dict(source_collision=str(source),source_sha256=hub.scan.digest(source),candidate_collision=str(target),candidate_sha256=hub.scan.digest(target),records=records,source_arena_triangles=scene_triangles(d),candidate_arena_triangles=scene_triangles(td),placed_triangles_saved=saving,unchanged_mesh_owners_exact=exact,field_native_remaining_mesh_triangles=before['field_native_mesh_triangles']-saving,field_native_shape_counts=before['field_native_shape_counts'],field_diagnostic_triangles=stage['placed_collision_triangles'],collision_representation='Closed low-triangle extruded profiles remain mesh-backed; no new native leaves.',input_pins={str(path):hub.scan.digest(path)for path in [source,STAGE,ROOT/'rules/collision-core-head-rune-reviewed-rmuc2027.json']},installed=False,contact_validated=False)
 (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print('Dart sides saved',saving,'placed triangles; arena',scene_triangles(d),'->',scene_triangles(td),flush=True)
 for row in records:print(row['node'],row['selected_triangles'],'to',row['proxy_triangles'],'triangles;',row['convex_regions'],'closed regions',flush=True)
if __name__=='__main__':main()
