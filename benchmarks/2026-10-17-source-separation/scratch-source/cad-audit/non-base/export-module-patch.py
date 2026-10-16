# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,json,numpy as np
from pathlib import Path
sys.path.insert(0,'../rm-map-tools/python')
from cad_document import CadDocument
from cad_components import export_selection
from validate_parts import read_part
from mesh_parts import tessellate
from export_field_package import GlbWriter
from gltf_scene import read_glb
base=Path('local-assets/cad-components/rmuc2027/full-separation-v1')
catalog=json.load(open('local-assets/cad-components/rmuc2027/catalog-regions-v1.json'))
sel=json.load(open(base/'outpost/components/rotor/module-0/selection.json'))
sel['components'].append(next(c for c in catalog['components'] if c['body_id']==2101579))
fs=json.load(open('local-assets/cad-audit/non-base/module-face-candidates.json'))[0]['face_ids']
out=Path('local-assets/cad-components/rmuc2027/module-0-face-candidate')
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as d:
 export_selection(d,sel,out,shell_ids_by_body={2601775:[2498962]},face_ids_by_body={2101579:fs})
print('exported source patch',len(fs),flush=True)
native,reader,error=read_part(str(out/'source.step'));assert not error,error
stats={};p,t,c,k=tessellate(native,.4,.25,stats=stats);print('tessellated',len(t),stats,flush=True)
orig,b=read_glb(base/'outpost/components/rotor/module-0/visual.glb')
rot=np.array(orig['nodes'][1]['matrix']).reshape(4,4,order='F')
w=GlbWriter('Outpost module 0 face candidate',orig['asset'])
w.add_node('module-0 including upper-body face patch',p/1000,t,[k[int(i)] for i in c],matrix=rot)
w.write(out/'visual.glb')
