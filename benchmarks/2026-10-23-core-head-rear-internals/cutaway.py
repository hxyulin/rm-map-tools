"""Matched internal mechanism views with outer skins/backing hidden for review."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from rear import b,BASE
r=json.loads((b.OUT/'rear-internals/verification.json').read_text());old=json.loads(BASE.read_text());survey=json.loads((b.ROOT/'out/rmuc2027-core-head-back-trial/survey.json').read_text())
ref=b.p.module('rear_cutaway_render_helpers',str(b.ROOT/'benchmarks/2026-10-23-core-head-back-trial/survey.py'));f=ref.f;raster=ref.raster
excluded={81,82,108,1254,1255,1266,1268};installed=Path(survey['source']);d,c,n=b.scan.load_nodes(installed)
ids={1270,1662,1503,1668,1284,1296,1297,1501};assert ids<=set(n)
rows=[]
with tempfile.TemporaryDirectory()as tmp:
 tmp=Path(tmp);data={'installed':list(f.load(str(installed),survey['placement'],ids))}
 for name,report in [('previous',old),('candidate',r)]:
  recipe=json.loads(Path(report['native_review']).read_text());shapes=[x['shape']for x in recipe['native_parts']if x.get('source_group')]
  labels=report['definition']['labels'];g=np.concatenate([b.v.geometry(s)for s,label in zip(shapes,labels)if label not in ['simplified recessed side panel','simple notched backing plate']])
  cut=tmp/(name+'.glb');b.p.replace(Path(report['candidate_collision']),cut,{1668:g})
  data[name]=list(f.load(str(cut),survey['placement'],{1668,1284,1296,1297,1501}))
 for name,a in data.items():
  a[1][:]=[.58,.60,.63]
  if name!='installed':a[1][a[4]==1668]=[.77,.42,.19]if name=='candidate'else[.16,.63,.84]
 frame=np.concatenate([a[0]for a in data.values()])
 for view in survey['views']:
  if view['camera']=='front':continue
  for name,a in data.items():
   path=b.OUT/f'cutaway-{view["camera"]}-{name}.webp'
   Image.fromarray(raster.raster(tuple(a),frame,view['direction'],b.ROOT/'out/rmuc2027-conservative-shape-audit/raster',tmp)).save(path,lossless=True)
   rows.append(dict(stage=name,camera=view['camera'],path=str(path),sha256=b.scan.digest(path)))
(b.OUT/'cutaway-renders.json').write_text(json.dumps(dict(source=str(installed),source_sha256=b.scan.digest(installed),views=rows,note='Selected source motor/support and socket parts only. Outer skins, broad interface frame and backing plate hidden for inspection only. Visual assets unchanged.'),indent=2)+'\n')
print('Rendered',len(rows),'matched internal cutaways.')
