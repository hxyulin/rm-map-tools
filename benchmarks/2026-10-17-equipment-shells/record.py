#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record source-pinned compact evidence without storing generated CAD meshes."""
import argparse
import json
from pathlib import Path
from common import ROOT
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());details=json.loads((out/'detail-summary.json').read_bytes());validation=json.loads((out/'validation.json').read_bytes());review=json.loads((out/'review.json').read_bytes());folder=Path(__file__).parent
    for report,producer in [(summary,'compose.py'),(validation,'validate.py'),(review,'review.py')]:
        if report['producer_sha256']!=digest(folder/producer):raise ValueError('stale producer')
    if validation['detail_summary_sha256']!=digest(out/'detail-summary.json')or review['summary_sha256']!=digest(out/'summary.json'):raise ValueError('stale derived checks')
    if digest(out/'candidate-field.glb')!=summary['assembly']['glb_sha256']:raise ValueError('full candidate changed')
    reports={r['id']:r for r in validation['components']};components=[];previous=json.loads((ROOT/'out/rmuc2027-dart-outpost/summary.json').read_bytes());old={r['id']:r for r in previous['components']};known={r['id']:r for r in summary['components']}
    for row in details['components']:
        cid=row['id'];proof=reports[cid]
        for name,sha in row['producer_sha256'].items():
            if digest(ROOT/name)!=sha:raise ValueError('detail producer changed')
        for name,sha in proof['output_sha256'].items():
            if digest(out/cid/name)!=sha:raise ValueError('validated output changed')
        components.append({key:row[key]for key in ['id','uses','before_visual','after_micro','after_visual','before_collision','after_collision','source_visual_sha256','source_collision_sha256','micro_glb_sha256','visual_glb_sha256','collision_glb_sha256']})
        if row.get('end_cap_envelopes'):
            caps=row['end_cap_envelopes']
            if digest(folder/'caps.py')!=caps['producer_sha256']or digest(ROOT/'python/cad_profile_envelope.py')!=caps['pass_sha256']:raise ValueError('cap producer changed')
            components[-1]['end_cap_envelopes']=caps
        components[-1]['selected_collision_triangles']=known[cid]['collision_budget_per_definition']
    visibility=json.loads((out/'optical-guards.json').read_bytes());applied=json.loads((out/'applied-optical-guards.json').read_bytes())
    if not visibility['passes_light_mask_guard']or visibility['candidate_full_glb_sha256']!=summary['assembly']['glb_sha256']or visibility['producer_sha256']!=digest(folder/'guard_lights.py'):raise ValueError('stale or failing assembled light-mask guard')
    changed={r['id']for r in components};exact=0
    for row in summary['components']:
        if digest(ROOT/row['visual_glb'])!=row['visual_sha256']:raise ValueError('visual changed')
        if row['id']not in changed:
            if row['visual_sha256']!=old[row['id']]['visual_sha256']:raise ValueError('unselected visual changed')
            exact+=1
        if row['collision_glb']and digest(ROOT/row['collision_glb'])!=row['collision_sha256']:raise ValueError('collision budget changed')
    if exact!=106:raise ValueError('unexpected composition scope')
    result={'totals':summary['totals'],'prior_totals':summary['prior_totals'],'groups':summary['groups'],'full_glb':summary['full_glb'],'assembly':summary['assembly'],'components':components,'exact_other_visual_definitions':exact,'validation':validation,'review':review,'optical_visibility':visibility,'applied_optical_guards':applied,'scope':summary['scope'],'producer_sha256':{str(p.relative_to(ROOT)):digest(p)for p in [*folder.glob('*.py'),ROOT/'python/cad_component_detail.py',ROOT/'python/cad_profile_envelope.py',ROOT/'python/cad_dense_lod.py',ROOT/'python/test_cad_component_detail.py',ROOT/'python/test_cad_equipment_selection.py',ROOT/'python/test_cad_profile_envelope.py']},'report_sha256':{name:digest(out/name)for name in ['summary.json','detail-summary.json','validation.json','review.json','composition.json','optical-guards.json','applied-optical-guards.json']}}
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(result['totals'])


if __name__=='__main__':main()
