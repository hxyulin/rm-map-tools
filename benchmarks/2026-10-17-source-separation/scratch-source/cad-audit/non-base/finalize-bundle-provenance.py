# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Stamp upstream notices into an existing work bundle, preserving all binary geometry."""
import sys,json,hashlib,shutil
from pathlib import Path
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
from gltf_scene import read_glb,write_glb
import provenance
root=Path('local-assets/cad-components/rmuc2027/full-separation-v1')
manifest=json.loads((root/'manifest.json').read_text());changes=[]
for product in manifest['products']:
 for relative in [product['full_visual']]+[g['directory']+'/visual.glb' for g in product['groups']]:
  file=root/product['name']/relative
  doc,binary=read_glb(file);original=hashlib.sha256(binary).hexdigest()
  prior=doc['asset']['extras']
  doc['asset']=provenance.glb_asset('cad_partition.py','RMUC2027_V1.0.0.stp',manifest['source_sha256'],**{k:v for k,v in prior.items() if k!='source_sha256'})
  write_glb(file,doc,binary)
  reread,payload=read_glb(file);assert hashlib.sha256(payload).hexdigest()==original
  changes.append({'file':str(file.relative_to(root)),'binary_sha256_unchanged':original})
shutil.copyfile('../rm-map-tools/NOTICE.md',root/'NOTICE.md')
manifest['post_export_metadata']={'kind':'upstream-provenance-only','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'geometry_binary_preserved':changes,'current_exporter_sha256':hashlib.sha256(Path('../rm-map-tools/python/cad_partition.py').read_bytes()).hexdigest()}
manifest['files_sha256']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Upstream provenance preserved;',len(changes),'GLB binary buffers unchanged')
