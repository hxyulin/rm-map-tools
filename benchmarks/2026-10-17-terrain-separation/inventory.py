# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
# Diagnostic helper: run from rm-map-tools; writes disposable out/terrain-review reports.
import sys,json,numpy as np,collections
from pathlib import Path
sys.path.insert(0,str(Path('python').resolve()))
from p21index import build_index
from cad_document import CadDocument
from cad_components import build_catalog
cache=Path('out/terrain-review/source.npz');data=build_index('source/RMUC2027_V1.0.0.stp',workers=1);np.savez(cache,**data);del data
policy=json.load(open('rules/components-rmuc2027.json'));motion=json.load(open('rules/reviewed-motion-rmuc2027.json'));regions=json.load(open('rules/component-regions-rmuc2027.json'))
with CadDocument.from_index(cache,expected_sha256=policy['source_sha256']) as d:
 c=build_catalog(d,policy,motion,regions);Path('out/terrain-review/catalog.json').write_text(json.dumps(c,indent=2))
 excluded={1354629,1751926,2603236,3749800,3998852,4056216,4774244}
 records=[]
 for b,rep in d.model.bodies:
  pid=int(d.index.ids[d.model.rep_product[rep]])
  if pid in excluded:continue
  lo,hi,n=d.model.body_bbox(b);bid=int(d.index.ids[b]);r=dict(product_id=pid,name=policy['product_names'][str(pid)],body_id=bid,kind=d.index.tname(b),faces=len(d.model.body_faces(b)),min_mm=lo.tolist(),max_mm=hi.tolist())
  if r['kind']=='SHELL_BASED_SURFACE_MODEL':r['shells']=[{'id':int(s),'faces':len(d.model.body_faces(d.index.r(int(s))))} for s in d.index.refs_of(b)]
  records.append(r)
 Path('out/terrain-review/inventory.json').write_text(json.dumps(records,indent=2))
 for pid in sorted({r['product_id'] for r in records}):
  body=[r for r in records if r['product_id']==pid];print(pid,body[0]['name'],len(body),'bodies',sum(r['faces'] for r in body),'faces',dict(collections.Counter(r['kind'] for r in body)),flush=True)
 print('TOTAL',len(records),sum(r['faces'] for r in records),'faces',flush=True)
