"""Conservative projected profiles for Dart frame sides; preserve large openings."""
import json,sys,time
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles
from shapely.strtree import STRtree
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-rune-hub-solid-trial'))
import hub
from gltf_scene import read_glb,accessor,scene_nodes
OUT=ROOT/'out/rmuc2027-dart-side-profiles'
STAGE=ROOT/'out/rmuc2027-rune-hub-projectile-cover/paired-stage.json'

def split_profile(g,sign):
 mask=(g[:,:,0]>=340.).all(1)if sign>0 else(g[:,:,0]<=-340.).all(1)
 selected=g[mask];xy=np.round(selected[:,:,1:],3);polys=[Polygon(t)for t in xy if abs((t[1,0]-t[0,0])*(t[2,1]-t[0,1])-(t[1,1]-t[0,1])*(t[2,0]-t[0,0]))>1e-6];raw=unary_union(polys)
 def clean(poly):return Polygon(poly.exterior,[ring.coords for ring in poly.interiors if Polygon(ring).area>250.])
 geoms=list(raw.geoms)if raw.geom_type=='MultiPolygon'else[raw];filled=unary_union([clean(p)for p in geoms])
 return mask,selected,raw,filled

def partition(poly):
 pieces=list(constrained_delaunay_triangles(poly).geoms)
 while True:
  tree=STRtree(pieces);done=False
  for i,piece in enumerate(pieces):
   for j in tree.query(piece,predicate='touches'):
    j=int(j)
    if j<=i:continue
    other=pieces[j];union=piece.union(other)
    if union.geom_type=='Polygon'and union.convex_hull.area-union.area<1e-5:
     pieces=[p for k,p in enumerate(pieces)if k not in [i,j]]+[union.convex_hull];done=True;break
   if done:break
  if not done:return pieces

def main():
 OUT.mkdir(exist_ok=True);stage=json.loads(STAGE.read_text());path=Path(stage['collision_assets']['arena-static']['path']);d,b=read_glb(path);g=np.concatenate([accessor(d,b,pr['attributes']['POSITION'])[accessor(d,b,pr['indices']).reshape(-1,3)].astype(float)*1000 for pr in d['meshes'][d['nodes'][354]['mesh']]['primitives']]);rows=[]
 for sign in [-1,1]:
  mask,selected,raw,filled=split_profile(g,sign)
  for tolerance in [1.,2.,4.]:
   start=time.monotonic();profile=filled.simplify(tolerance,preserve_topology=True).buffer(tolerance+.25,join_style=2);missing=raw.difference(profile).area;parts=partition(profile)
   row=dict(side=sign,triangles_selected=int(mask.sum()),source_profile_area_mm2=raw.area,profile_area_mm2=profile.area,missing_area_mm2=missing,native_convex_pieces=len(parts),tolerance_mm=tolerance,elapsed_s=time.monotonic()-start,x_bounds_mm=[float(selected[:,:,0].min()),float(selected[:,:,0].max())]);rows.append(row);print(row,flush=True)
 (OUT/'study.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':main()
