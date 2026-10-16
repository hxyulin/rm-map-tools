# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,json,numpy as np,collections
sys.path.insert(0,'../rm-map-tools/python')
from cad_document import CadDocument
out=[]
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as d:
 ix=d.index;m=d.model
 for pid,bid in [(1751926,1751911),(3749800,3749315),(3998852,3998604)]:
  shells=[]
  for sid in d.entity(bid).reference_ids:
   r=ix.r(int(sid));lo,hi,n=m.body_bbox(r);fs=list(m.body_faces(r));shells.append(dict(product_id=pid,body_id=bid,shell_id=int(sid),face_count=len(fs),min_mm=lo.tolist(),max_mm=hi.tolist()))
  print('BODY',bid,'shells',len(shells),flush=True)
  for v in sorted(shells,key=lambda s:s['face_count'],reverse=True)[:24]:print(v['shell_id'],v['face_count'],np.round(v['min_mm'],1),np.round(v['max_mm'],1),flush=True)
  out.extend(shells)
 json.dump(out,open('local-assets/cad-audit/non-base/remaining-shell-bounds.json','w'),indent=2)
