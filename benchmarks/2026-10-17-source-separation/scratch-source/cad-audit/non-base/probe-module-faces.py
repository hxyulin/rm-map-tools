# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,json,numpy as np
sys.path.insert(0,'../rm-map-tools/python')
from cad_document import CadDocument
p=json.load(open('local-assets/cad-components/rmuc2027/full-separation-v1/partition.json'))['products'][0]
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as d:
 ix=d.index;m=d.model;result=[]
 bounds=[(f,*m.body_bbox(f)[:2]) for f in m.body_faces(ix.r(2101579))]
 for g in p['groups']:
  if '/module-' not in g['id']:continue
  shell=g['shell_ids_by_body']['2601775'][0];lo,hi,n=m.body_bbox(ix.r(shell))
  for pad in [2.1,5,10]:
   fs=[f for f,a,b in bounds if a is not None and np.all(a>=lo-pad) and np.all(b<=hi+pad)]
   print(g['id'],pad,len(fs),m.face_colour_hist(ix.r(2101579),fs),flush=True)
   if pad==5:result.append(dict(group=g['id'],body_id=2101579,face_ids=[int(ix.ids[f]) for f in fs],min_mm=(lo-pad).tolist(),max_mm=(hi+pad).tolist()))
 json.dump(result,open('local-assets/cad-audit/non-base/module-face-candidates.json','w'),indent=2)
