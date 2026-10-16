# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verify file integrity, gzip round trips, source face coverage and GLB recomposition."""
import sys,json,gzip,hashlib,collections
from pathlib import Path
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
import numpy as np
from cad_document import CadDocument
from gltf_scene import read_glb,scene_nodes,accessor
root=Path('local-assets/cad-components/rmuc2027/full-separation-v1')
manifest=json.loads((root/'manifest.json').read_text());partition=json.loads((root/'partition.json').read_text())
def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
for name,expected in manifest['files_sha256'].items():assert digest(root/name)==expected,name
packed=0
for sidecar in root.rglob('selection.json'):
 metadata=json.loads(sidecar.read_text())
 with gzip.open(sidecar.parent/'source.step.gz','rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
 assert actual==metadata['work_step_sha256'],str(sidecar)
 packed+=1
records=[]
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz',expected_sha256=manifest['source_sha256']) as doc:
 for product in partition['products']:
  expected={int(doc.index.ids[f]) for b,r in doc.model.bodies if doc.model.rep_product.get(r)==doc.index.r(product['product_id']) for f in doc.model.body_faces(b)}
  counts=collections.Counter(f for g in product['groups'] for f in g['face_ids'])
  assert set(counts)==expected and set(counts.values())=={1}
  for unit in product['units']:
   row=doc.index.r(unit['shell_id'] if unit['shell_id'] is not None else unit['body_id'])
   assert set(unit['face_ids'])=={int(doc.index.ids[f]) for f in doc.model.body_faces(row)}
  pd=next(p for p in manifest['products'] if p['name']==product['name'])
  full,binary=read_glb(root/pd['name']/pd['full_visual'])
  nodes={full['nodes'][i]['extras']['cad_partition']['group']:(i,world) for i,world,parent in scene_nodes(full) if 'mesh' in full['nodes'][i]}
  assert set(nodes)=={g['id'] for g in pd['groups']}
  for group in pd['groups']:
   part,payload=read_glb(root/pd['name']/group['directory']/'visual.glb')
   placed=[(i,m) for i,m,parent in scene_nodes(part) if 'mesh' in part['nodes'][i]]
   assert len(placed)==1
   pi,pworld=placed[0];fi,fworld=nodes[group['id']]
   assert np.array_equal(pworld,fworld)
   fp=full['meshes'][full['nodes'][fi]['mesh']]['primitives'];pp=part['meshes'][part['nodes'][pi]['mesh']]['primitives']
   assert len(fp)==len(pp)
   for a,b in zip(fp,pp):
    assert a['attributes'].keys()==b['attributes'].keys()
    for attr in a['attributes']:assert np.array_equal(accessor(full,binary,a['attributes'][attr]),accessor(part,payload,b['attributes'][attr]))
    assert np.array_equal(accessor(full,binary,a['indices']),accessor(part,payload,b['indices']))
    assert full['materials'][a['material']]==part['materials'][b['material']]
  records.append({'product':product['name'],'source_faces':len(expected),'groups':len(pd['groups']),'source_coverage_exactly_once':True,'full_and_parts_geometry_normals_materials_and_transforms_equal':True})
result={'file_checksums_verified':len(manifest['files_sha256']),'gzip_round_trips_verified':packed,'products':records}
Path('local-assets/cad-audit/non-base/full-bundle-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
