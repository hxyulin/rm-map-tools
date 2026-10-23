"""Verify delta from the accepted simple side-recess trial."""
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from rear import b,BASE
helpers=b.p.module('rear_check_helpers',str(b.ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/verify.py'))
r=json.loads((b.OUT/'rear-internals/verification.json').read_text());old=json.loads(BASE.read_text())
a=json.loads(Path(r['native_review']).read_text());o=json.loads(Path(old['native_review']).read_text())
parts=[x['shape']for x in a['native_parts']if x.get('source_group')];oldparts=[x['shape']for x in o['native_parts']if x.get('source_group')]
labels=r['definition']['labels'];oldlabels=old['definition']['labels']
for label in ['coarse rear support','simplified recessed side panel']:
 assert [s for s,l in zip(parts,labels)if l==label]==[s for s,l in zip(oldparts,oldlabels)if l==label]
# Exhaustive cells of the orthogonal motor-box arrangement prove containment,
# because membership in axis-aligned boxes is constant inside each grid cell.
oldmotor=[s for s,l in zip(oldparts,oldlabels)if l=='motor housing with approach clearance'];newmotor=[s for s,l in zip(parts,labels)if l=='consolidated motor housing']
bounds=[]
for shape in oldmotor+newmotor:
 c=np.array(shape['pose']['translation_m'])*1000;e=np.array(shape['half_extents_m'])*1000;bounds.extend([c-e,c+e])
axes=[np.unique(np.array(bounds)[:,i].round(7))for i in range(3)]
mid=[(a[1:]+a[:-1])/2 for a in axes];probes=np.array([[x,y,z]for x in mid[0]for y in mid[1]for z in mid[2]])
oldinside=np.logical_or.reduce([helpers.covered(probes,s)for s in oldmotor]);newinside=np.logical_or.reduce([helpers.covered(probes,s)for s in newmotor]);assert not (oldinside&~newinside).any()
newgeom=np.concatenate([b.v.geometry(s)for s in newmotor]);oldgeom=np.concatenate([b.v.geometry(s)for s in oldmotor]);samples=b.p.probes(newgeom,15000)
oldinside_samples=np.logical_or.reduce([helpers.covered(samples,s)for s in oldmotor]);distance=b.p.distances(samples[~oldinside_samples],oldgeom.reshape(-1,3),np.arange(len(oldgeom)*3).reshape(-1,3))
# The large lower-left backing-plate notch stays open across the plate thickness.
p=r['definition']['backing_plate'];normal=np.array(p['front_normal']);offset=p['front_plane_offset_mm'];xy=np.array([[x,y]for x in np.linspace(-669,-635,12)for y in np.linspace(-1093,-1037,20)])
face=np.column_stack([xy,(offset-xy@normal[:2])/normal[2]]);notch=np.concatenate([face-normal*d for d in [-1,0,4,8,9]])
assert not any(helpers.covered(notch,s,strict=True).any()for s in parts)
# Both simplified side recesses still pass their existing five-depth test.
import sys
sys.path.insert(0,str(b.ROOT/'benchmarks/2026-10-23-core-head-side-clearance'))
from shapely.geometry import Point
opening_samples=0
for p in r['definition']['simplified_side_panels']:
 hole=Polygon(p['hole_xy_mm']).buffer(-8);normal=np.array(p['normal']);offset=p['front_plane_offset_mm']
 xy=np.array([[x,y]for x in np.arange(hole.bounds[0],hole.bounds[2],5)for y in np.arange(hole.bounds[1],hole.bounds[3],5)if hole.contains(Point(x,y))])
 face=np.column_stack([xy,(offset-xy@normal[:2])/normal[2]]);pts=np.concatenate([face-normal*d for d in [-1,0,1,2,3]])
 assert not any(helpers.covered(pts,s,strict=True).any()for s in parts);opening_samples+=len(pts)
source=Path(r['source_collision']);_,_,n=b.scan.load_nodes(source)
plategeom=np.concatenate([b.v.geometry(s)for s,l in zip(parts,labels)if l=='simple notched backing plate'])
plate_source=b.p.probes(n[81],10000);plate_new=b.p.probes(plategeom,10000)
forward=b.p.distances(plate_source,plategeom.reshape(-1,3),np.arange(len(plategeom)*3).reshape(-1,3));reverse=b.p.distances(plate_new,n[81].reshape(-1,3),np.arange(len(n[81])*3).reshape(-1,3))
proof=dict(unchanged_side_recess_and_three_rear_boxes=True,motor_boxes_before=len(oldmotor),motor_boxes_after=len(newmotor),motor_old_volume_contained_in_new=True,exact_grid_cells=len(probes),
 motor_new_surface_outside_previous_union_max_sampled_mm=float(distance.max()),backing_notch_clearance_samples=len(notch),side_recess_clearance_samples=opening_samples,
 backing_source_to_new_surface_max_sampled_mm=float(forward.max()),backing_new_to_source_surface_max_sampled_mm=float(reverse.max()),
 caveat='Finite surface and clearance samples; stepped motor sides fill extra space. Contact changes elsewhere remain reported in geometry-verification.json.')
(b.OUT/'rear-internals/delta-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
