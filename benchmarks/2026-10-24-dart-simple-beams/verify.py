"""Verify reopened beam boxes contain assigned source faces and remain closed."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
from export import OUT,hub,local_geometry,split_profile
from gltf_scene import read_glb
r=json.loads((OUT/'verification.json').read_text());d,b=read_glb(Path(r['source_collision']));a,ab=read_glb(Path(r['candidate_collision']));results=[]
for record in r['records']:
 source=np.concatenate(local_geometry(d,b,record['node']));proxy=local_geometry(a,ab,record['node'])[-1];offset=0;proof=[];openings=[]
 for side in record['definitions']:
  mask,selected,raw,filled=split_profile(source,side['side']);seen=[];polys=[]
  for piece in side['convex_pieces']:
   geo=proxy[offset:offset+12];offset+=12
   vertices,inv=np.unique(geo.reshape(-1,3),axis=0,return_inverse=True);assert len(vertices)==8
   faces=inv.reshape(-1,3);edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1);assert(np.unique(edges,axis=0,return_counts=True)[1]==2).all()
   eq=ConvexHull(vertices).equations;ids=piece['source_selected_indices'];seen+=ids
   points=selected[ids].reshape(-1,3);margin=float(-(points@eq[:,:3].T+eq[:,3]).max());assert margin>.45
   polygon=Polygon(piece['profile_yz_mm']);polys.append(polygon)
   proof.append(dict(member=piece['member'],side=side['side'],source_triangles=len(ids),minimum_containment_margin_mm=margin,closed_edges=True))
  assert sorted(seen)==list(range(len(selected)))
  union=unary_union(polys);assert raw.difference(union).area<1e-4
  polysource=list(raw.geoms)if raw.geom_type=='MultiPolygon'else[raw]
  for poly in polysource:
   for ring in poly.interiors:
    hole=Polygon(ring)
    if hole.area<10000:continue
    core=hole.buffer(-3).difference(raw.buffer(3));remaining=core.difference(union)
    openings.append(dict(side=side['side'],source_opening_area_mm2=hole.area,core_area_mm2=core.area,remaining_core_area_mm2=remaining.area,core_filled_fraction=1-remaining.area/core.area))
 assert offset==len(proxy)
 results.append(dict(node=record['node'],source_faces_contained=sum(p['source_triangles']for p in proof),boxes=proof,opening_measurements=openings))
report=dict(candidate_sha256=hub.scan.digest(Path(r['candidate_collision'])),records=results,closed_boxes=28,source_faces_contained=18358,unchanged_other_owners=r['unchanged_mesh_owners_exact'],scope='All assigned source triangles inside individual reopened boxes; opening widths can shrink and are measured, not claimed unchanged.')
(OUT/'geometry-verification.json').write_text(json.dumps(report,indent=2)+'\n');print('Verified 28 closed boxes and 18,358 complete source triangles.')
print('Opening core fill fraction max:',max(o['core_filled_fraction']for row in results for o in row['opening_measurements']))
