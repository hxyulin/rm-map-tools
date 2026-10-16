# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,collections
sys.path.insert(0,'../rm-map-tools/python')
from cad_document import CadDocument
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as d:
 ix=d.index;m=d.model
 for bid in [2101579,1920483]:
  print('BODY',bid,ix.text(ix.r(bid))[:400],flush=True)
  shells=collections.Counter(s for f,s in m.body_faces_shells(ix.r(bid)))
  for shell,n in shells.items():
   lo,hi,nv=m.body_bbox(shell);print('SHELL',int(ix.ids[shell]),n,lo,hi,flush=True)
