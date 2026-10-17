#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Globally audit source mounting-opening and fastener candidates, without edits."""
import argparse,hashlib,json,time
from pathlib import Path
from collections import defaultdict
from cad_document import CadDocument
from cad_mounting_details import mounting_details


def audit(source,output,*,source_sha256,hierarchy=None,workers=1,maximum_diameter_mm=17,
          maximum_fastener_length_mm=60,maximum_slot_length_mm=60):
    """Write a new read-only report; optional hierarchy gives work-part membership."""
    if output.exists():raise FileExistsError(output)
    started=time.perf_counter();loader=CadDocument.from_step if source.suffix.lower() in {'.step','.stp'} else CadDocument.from_index
    options={'expected_sha256':source_sha256}
    if loader==CadDocument.from_step:options.update(workers=workers,intern_layers=True)
    with loader(source,**options) as document:
        print('source loaded; inspecting all body definitions',flush=True)
        findings=mounting_details(document,maximum_diameter_mm=maximum_diameter_mm,maximum_fastener_length_mm=maximum_fastener_length_mm,maximum_slot_length_mm=maximum_slot_length_mm)
        component_counts=defaultdict(lambda:{'opening_mouths':0,'possible_fastener_units':0});membership={};hierarchy_hash=None
        if hierarchy:
            catalog=json.loads(hierarchy.read_bytes())
            if catalog.get('files_sha256',{}).get('field.step')!=document.source_sha256:raise ValueError('hierarchy does not describe this source STEP')
            hierarchy_hash=hashlib.sha256(hierarchy.read_bytes()).hexdigest()
            for component in catalog['components']:
                for body in component['export_body_ids'].values():membership.setdefault(int(body),set()).add(component['id'])
        for field,rows in [('opening_mouths',findings['openings']),('possible_fastener_units',findings['fasteners'])]:
            for row in rows:
                components=sorted({c for body in row['source_body_ids'] for c in membership.get(body,())});row['components']=components
                for component in components:component_counts[component][field]+=1
        document.verify_source()
        report={'schema_version':1,'pass_id':'mounting-details','mode':'analysis-only','actions':[],
                'source_sha256':document.source_sha256,'source_bytes':document.index.size,'source_unchanged':True,
                'hierarchy_sha256':hierarchy_hash,'findings':findings,
                'components':[{'id':key,**value} for key,value in sorted(component_counts.items(),key=lambda item:(-sum(item[1].values()),item[0]))],
                'producer_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ['audit_mounting_details.py','cad_mounting_details.py','cad_document.py','cad_patch_matching.py','cad_optimizer.py','p21index.py','p21model.py']},
                'elapsed_seconds':time.perf_counter()-started,'scope':'All source definitions, terrain and equipment, no native healing/tessellation/removal. Body/shell/face/loop/edge IDs are STEP IDs scoped by source SHA, not native import ordinals. Analytic mounting/fastener candidates remain semantically unconfirmed. No placed triangle savings or physical-hole count claimed.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False);stream.write('\n')
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('source',type=Path);ap.add_argument('--source-sha256',required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--hierarchy',type=Path);ap.add_argument('--workers',type=int,default=1);ap.add_argument('--maximum-diameter-mm',type=float,default=17);ap.add_argument('--maximum-fastener-length-mm',type=float,default=60);ap.add_argument('--maximum-slot-length-mm',type=float,default=60);a=ap.parse_args()
    report=audit(a.source,a.out,source_sha256=a.source_sha256,hierarchy=a.hierarchy,workers=a.workers,maximum_diameter_mm=a.maximum_diameter_mm,maximum_fastener_length_mm=a.maximum_fastener_length_mm,maximum_slot_length_mm=a.maximum_slot_length_mm)
    f=report['findings'];print(json.dumps({'report':str(a.out),'opening_mouths':f['opening_mouths'],'circular_opening_mouths':f['circular_opening_mouths'],'narrow_opening_mouths':f['narrow_noncircular_opening_mouths'],'possible_fastener_units':f['possible_fastener_units'],'top_components':report['components'][:15],'source_unchanged':True},indent=2))
if __name__=='__main__':main()
