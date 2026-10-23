"""Check the explicitly filled gaps and unchanged important side openings."""
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,Point
from solid import b,BASE
helpers=b.p.module('solid_delta_helpers',str(b.ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/verify.py'))
r=json.loads((b.OUT/'solid-rear/verification.json').read_text());old=json.loads(BASE.read_text())
a=json.loads(Path(r['native_review']).read_text());o=json.loads(Path(old['native_review']).read_text())
parts=[x['shape']for x in a['native_parts']if x.get('source_group')];oldparts=[x['shape']for x in o['native_parts']if x.get('source_group')];labels=r['definition']['labels'];oldlabels=old['definition']['labels']
for label in ['coarse rear support','simplified recessed side panel']:
 assert [s for s,l in zip(parts,labels)if l==label]==[s for s,l in zip(oldparts,oldlabels)if l==label]
block=parts[labels.index('single solid lower block')]
for s,label in zip(oldparts,oldlabels):
 if label=='consolidated motor housing':assert helpers.covered(b.v.geometry(s).reshape(-1,3),block).all()
_,_,n=b.scan.load_nodes(Path(r['source_collision']));rod=parts[labels.index('solid rod cylinder')]
rodpoints=np.concatenate([n[1297],n[1501]]).reshape(-1,3)
assert helpers.covered(rodpoints,rod).all()
rodgeo=b.v.geometry(rod);source_rod=np.concatenate([n[1297],n[1501]])
reverse=b.p.distances(b.p.probes(rodgeo,20000),source_rod.reshape(-1,3),np.arange(len(source_rod)*3).reshape(-1,3))
plate=parts[labels.index('rectangular backing plate')];pg=b.v.geometry(plate)
forward=b.p.distances(b.p.probes(n[81],10000),pg.reshape(-1,3),np.arange(len(pg)*3).reshape(-1,3));back=b.p.distances(b.p.probes(pg,10000),n[81].reshape(-1,3),np.arange(len(n[81])*3).reshape(-1,3))
opening_samples=0
for p in r['definition']['simplified_side_panels']:
 hole=Polygon(p['hole_xy_mm']).buffer(-8);normal=np.array(p['normal']);offset=p['front_plane_offset_mm']
 xy=np.array([[x,y]for x in np.arange(hole.bounds[0],hole.bounds[2],5)for y in np.arange(hole.bounds[1],hole.bounds[3],5)if hole.contains(Point(x,y))])
 face=np.column_stack([xy,(offset-xy@normal[:2])/normal[2]]);pts=np.concatenate([face-normal*d for d in [-1,0,1,2,3]])
 assert not any(helpers.covered(pts,s,strict=True).any()for s in parts);opening_samples+=len(pts)
proof=dict(side_recess_frames_and_upper_support_boxes_exact=True,side_opening_samples=opening_samples,lower_block_contains_all_previous_motor_box_vertices=True,
 rod_source_vertices_inside_native_cylinder=True,rod_fit_to_source_max_sampled_mm=float(reverse.max()),plate_source_to_fit_max_sampled_mm=float(forward.max()),plate_fit_to_source_max_sampled_mm=float(back.max()),
 intentionally_closed=['Lower motor-housing channels and recesses','Backing plate notch and sloped roof corners','Rod axial bore and longitudinal slots'],
 caveat='Cylinder caps and solid volume deliberately change entry through the rod. Inherited housing-only approach checks exclude the new cylinder and lower block; visuals remain unchanged.')
(b.OUT/'solid-rear/delta-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
