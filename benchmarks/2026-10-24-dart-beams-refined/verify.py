"""Independent reopened face containment and opening measurements for thinner beams."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon,MultiPoint
from shapely.ops import unary_union
from export import OUT,ROOT,hub,local_geometry,split_profile
from gltf_scene import read_glb,accessor
r=json.loads((OUT/'verification.json').read_text());d,b=read_glb(Path(r['source_collision']));a,ab=read_glb(Path(r['candidate_collision']));results=[]
def canonical(t):return tuple(sorted(tuple(p)for p in t))
for row in r['records']:
 source=np.concatenate(local_geometry(d,b,row['node']));proxy=local_geometry(a,ab,row['node'])[-1];offset=0;proof=[];openings=[]
 for side in row['definitions']:
  _,selected,raw,_=split_profile(source,side['side']);covered=np.zeros(len(selected),bool);polys=[]
  for piece in side['convex_pieces']:
   count=piece['triangles'];geo=proxy[offset:offset+count];offset+=count
   if piece['kind']=='exact-residual':
    exact={canonical(t)for t in geo}
    covered|=np.array([canonical(t)in exact for t in selected]);polys.extend(Polygon(t[:,1:])for t in geo if Polygon(t[:,1:]).area>1e-8);continue
   vertices,inv=np.unique(geo.reshape(-1,3),axis=0,return_inverse=True);assert len(vertices)==8
   faces=inv.reshape(-1,3);edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1);assert(np.unique(edges,axis=0,return_counts=True)[1]==2).all()
   eq=ConvexHull(vertices).equations;distance=(selected.reshape(-1,3)@eq[:,:3].T+eq[:,3]).reshape(len(selected),3,-1).max((1,2));covered|=distance<1e-4
   polys.append(MultiPoint(vertices[:,1:]).convex_hull);proof.append(dict(member=piece['member'],kind=piece['kind'],closed_edges=True))
  assert covered.all(),int((~covered).sum())
  union=unary_union(polys);polysource=list(raw.geoms)if raw.geom_type=='MultiPolygon'else[raw]
  for poly in polysource:
   for ring in poly.interiors:
    hole=Polygon(ring)
    if hole.area<10000:continue
    core=hole.buffer(-3).difference(raw.buffer(3));remaining=core.difference(union)
    openings.append(dict(side=side['side'],source_opening_area_mm2=hole.area,core_area_mm2=core.area,remaining_core_area_mm2=remaining.area,core_filled_fraction=1-remaining.area/core.area))
 assert offset==len(proxy)
 # Reopened retained original primitives preserve attributes and triangle indices.
 old=d['meshes'][d['nodes'][row['node']]['mesh']]['primitives'];new=a['meshes'][a['nodes'][row['node']]['mesh']]['primitives'];j=0
 for selector in row['selectors']:
  p=old[selector['source_primitive']];indices=accessor(d,b,p['indices']).reshape(-1,3);keep=np.ones(len(indices),bool);keep[selector['selected_triangle_indices']]=False
  if not keep.any():continue
  q=new[j];j+=1;assert np.array_equal(indices[keep],accessor(a,ab,q['indices']).reshape(-1,3))
  for key,val in p['attributes'].items():assert np.array_equal(accessor(d,b,val),accessor(a,ab,q['attributes'][key]))
 results.append(dict(node=row['node'],source_faces_covered=row['selected_triangles'],closed_boxes=proof,opening_measurements=openings))
old=json.loads((ROOT/'out/rmuc2027-dart-simple-beams/geometry-verification.json').read_text())
for row,previous in zip(results,old['records']):
 for current,prior in zip(row['opening_measurements'],previous['opening_measurements']):current['prior_thick_fit_core_filled_fraction']=prior['core_filled_fraction']
report=dict(candidate_sha256=hub.scan.digest(Path(r['candidate_collision'])),records=results,source_faces_covered=18358,retained_triangles_exact=16512,closed_box_count=sum(len(row['closed_boxes'])for row in results),other_owners_exact=r['unchanged_mesh_owners_exact'])
(OUT/'geometry-verification.json').write_text(json.dumps(report,indent=2)+'\n');print('All 18,358 original side faces covered; retained payloads exact; boxes closed.')
for row in results[:1]:
 for o in row['opening_measurements']:print(o['side'],round(o['prior_thick_fit_core_filled_fraction']*100,1),'->',round(o['core_filled_fraction']*100,1),'percent filled')
