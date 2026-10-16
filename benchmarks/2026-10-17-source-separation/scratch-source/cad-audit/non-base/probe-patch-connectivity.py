# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,json,collections,numpy as np
sys.path.insert(0,'../rm-map-tools/python')
from cad_document import CadDocument
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as d:
 ix=d.index;m=d.model;report=[]
 for bid in [2101579]:
  selected=set(json.load(open('local-assets/cad-audit/non-base/module-face-candidates.json'))[int(sys.argv[1])]['face_ids']); faces=[f for f in m.body_faces(ix.r(bid)) if int(ix.ids[f]) in selected];parent={f:f for f in faces};edges={}
  def find(f):
   while parent[f]!=f:parent[f]=parent[parent[f]];f=parent[f]
   return f
  for f in faces:
   stack=[f];seen=set()
   while stack:
    r=stack.pop()
    if r in seen:continue
    seen.add(r);kind=ix.tname(r)
    if kind=='EDGE_CURVE':
     if r in edges:parent[find(f)]=find(edges[r])
     else:edges[r]=f
    elif kind in ['ADVANCED_FACE','FACE_BOUND','FACE_OUTER_BOUND','EDGE_LOOP','ORIENTED_EDGE']:
     stack.extend(ix.r(int(v)) for v in ix.refs_of(r))
  groups=collections.defaultdict(list)
  for f in faces:groups[find(f)].append(f)
  print('BODY',bid,'components',len(groups),flush=True)
  for fs in sorted(groups.values(),key=len,reverse=True):
   bounds=[m.body_bbox(f) for f in fs];bounds=[b for b in bounds if b[0] is not None]
   lo=np.min([b[0] for b in bounds],axis=0);hi=np.max([b[1] for b in bounds],axis=0)
   ids=[int(ix.ids[f]) for f in fs];print(len(fs),lo.round(3),hi.round(3),ids[:3],flush=True)
   report.append(dict(body_id=bid,face_ids=ids,min_mm=lo.tolist(),max_mm=hi.tolist()))
 json.dump(report,open('local-assets/cad-audit/non-base/module-face-components-'+sys.argv[1]+'.json','w'),indent=2)
