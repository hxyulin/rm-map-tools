# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
# Diagnostic helper: run from rm-map-tools; writes disposable out/terrain-review reports.
import sys,json,collections
from pathlib import Path
sys.path.insert(0,str(Path('python').resolve()))
from cad_document import CadDocument
items=json.load(open('out/terrain-review/inventory.json'));results=[]
with CadDocument.from_index('out/terrain-review/source.npz') as d:
 ix=d.index;m=d.model
 for item in items:
  faces=m.body_faces(ix.r(item['body_id']));parent={f:f for f in faces};edges={}
  def find(f):
   while parent[f]!=f:parent[f]=parent[parent[f]];f=parent[f]
   return f
  for f in faces:
   stack=[f];seen=set()
   while stack:
    row=stack.pop()
    if row in seen:continue
    seen.add(row);kind=ix.tname(row)
    if kind=='EDGE_CURVE':
     if row in edges:parent[find(f)]=find(edges[row])
     else:edges[row]=f
    elif kind in ('ADVANCED_FACE','FACE_BOUND','FACE_OUTER_BOUND','EDGE_LOOP','ORIENTED_EDGE'):
     stack.extend(ix.r(int(r)) for r in ix.refs_of(row))
  counts=collections.Counter(find(f) for f in faces)
  results.append(dict(body_id=item['body_id'],name=item['name'],connected_face_components=len(counts),face_counts=sorted(counts.values(),reverse=True)))
  if len(counts)>1:print(item['name'],item['body_id'],len(counts),sorted(counts.values(),reverse=True),flush=True)
Path('out/terrain-review/connectivity.json').write_text(json.dumps(results,indent=2))
