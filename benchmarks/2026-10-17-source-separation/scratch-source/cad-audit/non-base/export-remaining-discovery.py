# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import sys,json,numpy as np,hashlib,time
from pathlib import Path
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
from validate_parts import read_part
from mesh_parts import tessellate
from export_step_elements import shape_counts
from export_field_package import GlbWriter
import provenance
root=Path('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/split');parts=json.load(open(root/'parts.json'))['parts']
c=json.load(open('local-assets/cad-components/rmuc2027/catalog-regions-v1.json'))
out=Path('local-assets/cad-components/rmuc2027/remaining-discovery');out.mkdir(exist_ok=True);report=[]
for pid,name in [(1751926,'technology-core'),(3998852,'resource-area'),(3749800,'dart-station'),(4056216,'energy-unit')]:
 part=next(p for p in parts if p['product_id']==pid);native,reader,error=read_part(str(root/part['file']));assert not error,error
 counts=shape_counts(native);expected=sum(b['faces'] for b in part['bodies']);assert counts[1]==expected,(name,counts,expected)
 stats={};p,t,ci,keys=tessellate(native,.4,.25,stats=stats);assert not stats.get('unmeshed_faces') and not stats.get('degenerate_faces'),stats
 occ=next(o for o in c['occurrences'] if o['product_id']==pid) if any('product_id' in o for o in c['occurrences']) else next(o for o in c['occurrences'] if o['component_id'].startswith(f'p{pid}.'))
 rot=np.eye(4);rot[:3,:3]=np.array([[1.,0,0],[0,0,1],[0,-1,0]])@np.array(occ['source_world_matrix'])[:3,:3]
 w=GlbWriter(name,provenance.glb_asset(Path(__file__).name,'RMUC2027_V1.0.0.stp',c['source_sha256'],source_product_id=pid,frame='product local metres, source first occurrence rotation into Y up'))
 w.add_node(name,p/1000,t,[keys[int(i)] for i in ci],matrix=rot);w.write(out/(name+'.glb'))
 report.append(dict(product_id=pid,name=name,faces=counts[1],solids=counts[0],triangles=len(t),stats=stats))
 print(report[-1],flush=True);del native,reader,p,t,ci,w
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
