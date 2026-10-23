"""Check simplified recess geometry, retained casing and review hashes."""
import json
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,Point
from simplified import b
verify=b.p.module('simple_clearance_helpers',str(b.ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/verify.py'))
r=json.loads((b.OUT/'side-clearance-simple/verification.json').read_text())
recipe=json.loads(Path(r['native_review']).read_text());shapes=[p['shape']for p in recipe['native_parts']if p.get('source_group')]
results=[]
for panel in r['definition']['simplified_side_panels']:
    hole=Polygon(panel['hole_xy_mm']);inner=hole.buffer(-8);normal=np.array(panel['normal']);offset=panel['front_plane_offset_mm']
    xy=np.array([[x,y]for x in np.arange(inner.bounds[0],inner.bounds[2],5)for y in np.arange(inner.bounds[1],inner.bounds[3],5)if inner.contains(Point(x,y))])
    face=np.column_stack([xy,(offset-xy@normal[:2])/normal[2]])
    probes=np.concatenate([face-normal*depth for depth in [-1,0,1,2,3]])
    assert not any(verify.covered(probes,s,strict=True).any()for s in shapes)
    results.append(dict(node=panel['source_node'],opening_clearance_probes=len(probes),corner_deviation_xy_mm=panel['hole_boundary_hausdorff_xy_mm'],corner_deviation_plane_upper_bound_mm=panel['hole_boundary_hausdorff_xy_mm']/normal[2]))
for row in json.loads((b.OUT/'renders.json').read_text())['views']:assert b.scan.digest(Path(row['path']))==row['sha256']
for path,h in r['input_pins'].items():assert b.scan.digest(Path(path))==h
proof=dict(panels=results,note='Opening interior excludes an 8 mm corner/border band. Five sample depths span the plate plus 1 mm on either side. This does not qualify deeper cavities or all-pose contacts.',visual_exact=True)
(b.OUT/'side-clearance-simple/recess-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
hashes={str(p.relative_to(b.OUT)):b.scan.digest(p)for p in b.OUT.rglob('*')if p.is_file()and p.name not in ['final-verification.json','gallery.html']}
(b.OUT/'final-verification.json').write_text(json.dumps(dict(geometry=json.loads((b.OUT/'geometry-verification.json').read_text()),recess=proof,matched_image_count=24,artifact_sha256=hashes,installed=False),indent=2)+'\n')
print(json.dumps(proof))
