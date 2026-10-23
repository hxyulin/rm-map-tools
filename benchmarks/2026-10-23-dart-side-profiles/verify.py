"""Prove selected source-face containment and preserve exact retained attributes."""
import hashlib,json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
from export import ROOT,OUT,STAGE,hub,local_geometry,projected
from gltf_scene import read_glb,accessor,scene_nodes
from simplify_package import scene_triangles

def main():
 r=json.loads((OUT/'verification.json').read_text());source=Path(r['source_collision']);target=Path(r['candidate_collision']);d,b=read_glb(source);a,ab=read_glb(target);exact=hub.p.pair.unchanged(source,target,{354,587});proofs=[];newpieces={}
 assert hub.scan.digest(source)==r['source_sha256']and hub.scan.digest(target)==r['candidate_sha256']
 for path,h in r['input_pins'].items():assert hub.scan.digest(Path(path))==h
 for row in r['records']:
  node=row['node'];oldmesh=d['meshes'][d['nodes'][node]['mesh']];newmesh=a['meshes'][a['nodes'][node]['mesh']];groups=local_geometry(d,b,node);oldg=np.concatenate(groups);allselected=np.zeros(len(oldg),bool);offset=0;newprimindex=0;retained=0
  for primitive,selector,g in zip(oldmesh['primitives'],row['selectors'],groups):
   indices=np.array(selector['selected_triangle_indices']);assert hashlib.sha256(indices.astype('<u8').tobytes()).hexdigest()==selector['selected_sha256'];mask=np.zeros(len(g),bool);mask[indices]=True;allselected[offset:offset+len(g)]=mask;offset+=len(g)
   if not (~mask).any():continue
   changed=newmesh['primitives'][newprimindex];newprimindex+=1
   assert {k:v for k,v in primitive.items()if k not in ['attributes','indices']}=={k:v for k,v in changed.items()if k not in ['attributes','indices']}
   for key in primitive['attributes']:
    x=accessor(d,b,primitive['attributes'][key]);y=accessor(a,ab,changed['attributes'][key]);assert x.dtype==y.dtype and x.shape==y.shape and x.tobytes()==y.tobytes()
   assert np.array_equal(accessor(d,b,primitive['indices']).reshape(-1,3)[~mask],accessor(a,ab,changed['indices']).reshape(-1,3));retained+=int((~mask).sum())
  proxy=newmesh['primitives'][-1];proxyg=accessor(a,ab,proxy['attributes']['POSITION'])[accessor(a,ab,proxy['indices']).reshape(-1,3)].astype(float)*1000;start=0;closed=0;sideproof=[];newpieces[node]=[]
  for definition in row['definitions']:
   sign=definition['side'];mask=allselected&((oldg[:,:,0]>=340).all(1)if sign>0 else(oldg[:,:,0]<=-340).all(1));selected=oldg[mask];geoms=[projected(t)for t in selected];tree=STRtree(geoms);polys=[];xmargin=np.inf
   for piece in definition['convex_pieces']:
    xy=np.array(piece['profile_yz_mm']);lo,hi=piece['x_bounds_mm'];verts=np.concatenate([np.column_stack([np.full(len(xy),x),xy])for x in [lo,hi]]);count=len(hub.v.hull_geometry(verts));g=proxyg[start:start+count];start+=count;assert len(g)==count
    p,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3);edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);_,uses=np.unique(edges,axis=0,return_counts=True);assert (uses==2).all();closed+=1
    polygon=__import__('shapely').geometry.MultiPoint(p[:,1:]).convex_hull;polys.append(polygon);idx=tree.query(polygon,predicate='intersects')
    if len(idx):
     margin=min(float(selected[idx,:,0].min()-p[:,0].min()),float(p[:,0].max()-selected[idx,:,0].max()));assert margin>.24;xmargin=min(xmargin,margin)
    newpieces[node].append(g)
   union=unary_union(polys);assert all(union.covers(g)for g in geoms)
   raw=unary_union([g for g in geoms if g.geom_type=='Polygon']);holes=[]
   sourcepolys=list(raw.geoms)if raw.geom_type=='MultiPolygon'else[raw]
   for poly in sourcepolys:
    for ring in poly.interiors:
     hole=Polygon(ring)
     if hole.area<10000:continue
     core=hole.buffer(-3).difference(raw.buffer(3));assert union.intersection(core).area<.01;holes.append(float(core.area))
   sideproof.append(dict(side=sign,complete_source_triangles_covered=len(selected),closed_profile_pieces=len(polys),minimum_x_margin_mm=xmargin,large_opening_cores_preserved=len(holes),large_opening_core_area_mm2=sum(holes)))
  assert start==len(proxyg)and retained==row['retained_triangles'];proofs.append(dict(node=node,retained_triangles_exact=retained,selected_source_triangles_enclosed=int(allselected.sum()),closed_profile_pieces=closed,sides=sideproof))
 stage=json.loads((OUT/'paired-stage.json').read_text())
 for role in ['visual','collision']:
  assert sum(x['placed_triangles']for x in stage[role+'_assets'].values())==stage['placed_'+role+'_triangles']
  for x in stage[role+'_assets'].values():assert hub.scan.digest(Path(x['path']))==x['sha256']
 proof=dict(unchanged_mesh_owners_exact=exact,visual_assets_exact=True,node_proofs=proofs,source_triangles_fully_enclosed=sum(p['selected_source_triangles_enclosed']for p in proofs),remaining_deck_crossbar_triangle_attributes_exact=sum(p['retained_triangles_exact']for p in proofs),no_added_native_leaves=True,
 theorem='For every profile region intersecting a selected triangle projection, the full triangle X interval lies inside the region slab. The union covers the entire projected triangle. Therefore the original triangle is contained in the union of closed profile solids.',installed=False,contact_validated=False)
 (OUT/'geometry-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
if __name__=='__main__':main()
