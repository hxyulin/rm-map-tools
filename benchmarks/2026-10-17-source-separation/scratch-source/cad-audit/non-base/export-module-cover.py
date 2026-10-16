# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,json,numpy as np,hashlib,shutil
from pathlib import Path
sys.path.insert(0,'../rm-map-tools/python')
from cad_document import CadDocument
from cad_components import export_selection
from validate_parts import read_part
from mesh_parts import tessellate
from export_field_package import GlbWriter
from gltf_scene import read_glb
from cad_partition import _pack_step
from export_step_elements import shape_counts
import provenance
base=Path('local-assets/cad-components/rmuc2027/full-separation-v1')
catalog=json.load(open('local-assets/cad-components/rmuc2027/catalog-regions-v1.json'))
sel=json.load(open(base/'outpost/components/rotor/module-0/selection.json'))
sel['components'].append(next(c for c in catalog['components'] if c['body_id']==2101579))
fs=json.load(open('local-assets/cad-audit/non-base/module-face-components-0.json'))[0]['face_ids']
sel['partition_source_face_ids']=sorted(set(sel['partition_source_face_ids']) | set(fs))
sel['occurrences'].extend(o for o in catalog['occurrences'] if o['component_id']=='p2603236.b2101579')
sel['review_status']='cover face-patch candidate; original fused solid remains authority'
out=Path('local-assets/cad-components/rmuc2027/module-0-cover-candidate')
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as d:
 export_selection(d,sel,out,shell_ids_by_body={2601775:[2498962]},face_ids_by_body={2101579:fs})
print('exported source patch',len(fs),flush=True)
native,reader,error=read_part(str(out/'source.step'));assert not error,error
assert list(shape_counts(native)) == [5,4263]
stats={};p,t,c,k=tessellate(native,.4,.25,stats=stats);print('tessellated',len(t),stats,flush=True)
orig,b=read_glb(base/'outpost/components/rotor/module-0/visual.glb')
rot=np.array(orig['nodes'][1]['matrix']).reshape(4,4,order='F')
w=GlbWriter('Outpost module 0 cover candidate',provenance.glb_asset(Path(__file__).name,'RMUC2027_V1.0.0.stp',sel['source_sha256'],review_status=sel['review_status'],face_patch_count=len(fs)))
w.add_node('module-0 including upper-body face patch',p/1000,t,[k[int(i)] for i in c],matrix=rot)
w.write(out/'visual.glb')

assert not stats.get('unmeshed_faces') and not stats.get('degenerate_faces')
_pack_step(out)
shutil.copyfile('../rm-map-tools/NOTICE.md',out/'NOTICE.md')
report={'native_solids':5,'native_faces':4263,'triangles':len(t),'tessellation_stats':stats,
        'source_face_patch_body':2101579,'source_face_patch_ids':fs,
        'producer_sha256':{str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [__file__,'../rm-map-tools/python/cad_components.py','../rm-map-tools/python/p21split.py']},
        'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
