"""Expose the changed lower block, rod and backing plate in matched views."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from solid import b,BASE
r=json.loads((b.OUT/'solid-rear/verification.json').read_text());old=json.loads(BASE.read_text());survey=json.loads((b.ROOT/'out/rmuc2027-core-head-back-trial/survey.json').read_text())
ref=b.p.module('solid_rear_cutaway_helpers',str(b.ROOT/'benchmarks/2026-10-23-core-head-back-trial/survey.py'));f=ref.f;raster=ref.raster
rows=[]
with tempfile.TemporaryDirectory()as tmp:
 tmp=Path(tmp)
 for mode in ['mechanisms','with-plate']:
  data={}
  for name,report in [('previous',old),('candidate',r)]:
   recipe=json.loads(Path(report['native_review']).read_text());shapes=[x['shape']for x in recipe['native_parts']if x.get('source_group')];labels=report['definition']['labels']
   hidden={'simplified recessed side panel'}
   if mode=='mechanisms':hidden|={'simple notched backing plate','rectangular backing plate'}
   g=np.concatenate([b.v.geometry(s)for s,label in zip(shapes,labels)if label not in hidden]);cut=tmp/f'{mode}-{name}.glb';b.p.replace(Path(report['candidate_collision']),cut,{1668:g})
   a=list(f.load(str(cut),survey['placement'],{1668,1284,1296,1297,1501}));a[1][:]=[.58,.60,.63];a[1][a[4]==1668]=[.77,.42,.19]if name=='candidate'else[.16,.63,.84];data[name]=a
  frame=np.concatenate([a[0]for a in data.values()])
  for view in survey['views']:
   if view['camera']=='front':continue
   for name,a in data.items():
    path=b.OUT/f'{mode}-{view["camera"]}-{name}.webp';Image.fromarray(raster.raster(tuple(a),frame,view['direction'],b.ROOT/'out/rmuc2027-conservative-shape-audit/raster',tmp)).save(path,lossless=True)
    rows.append(dict(mode=mode,stage=name,camera=view['camera'],path=str(path),sha256=b.scan.digest(path)))
(b.OUT/'cutaway-renders.json').write_text(json.dumps(dict(views=rows,note='Outer casing and side panels hidden only for inspection. Mechanisms mode also hides backing plate. Actual candidate retains them.'),indent=2)+'\n');print('Rendered',len(rows),'matched cutaways.')
