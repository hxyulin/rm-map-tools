#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record compact reproducible measurements while leaving generated CAD ignored."""
import argparse
import json
from pathlib import Path
from run import ROOT
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());review=json.loads((out/'review.json').read_bytes());validation=json.loads((out/'validation.json').read_bytes());detail=json.loads((out/'detail-summary.json').read_bytes());source=Path(__file__).parent
    for report,producer in [(summary,'finalize.py'),(review,'review.py'),(validation,'openings.py'),(detail,'run.py')]:
        if report['producer_sha256']!=digest(source/producer):raise ValueError('stale producer report')
    for report in [review,validation]:
        if report['summary_sha256']!=digest(out/'summary.json'):raise ValueError('stale derived validation')
    if digest(out/'candidate-field.glb')!=summary['assembly']['glb_sha256']:raise ValueError('assembled candidate changed')
    proofs={r['id']:r for r in summary['proofs']};components=[]
    for row in detail['components']:
        folder=out/row['id']
        for name,sha in row['outputs_sha256'].items():
            if digest(folder/name)!=sha:raise ValueError('detail payload changed')
        final=next(r for r in summary['components']if r['id']==row['id']);proof=proofs[row['id']]
        if digest(ROOT/final['collision_glb'])!=final['collision_sha256']:raise ValueError('final contact payload changed')
        components.append({'id':row['id'],'uses':row['uses'],'reference_visual_triangles':row['before'],'candidate_visual_triangles':row['visual'],'reference_collision_triangles':row['previous_collision'],'candidate_collision_triangles':final['collision_budget_per_definition'],'source_step_sha256':row['source_step_sha256'],'source_visual_sha256':row['source_visual_sha256'],'source_npz_sha256':row['source_npz_sha256'],'candidate_visual_sha256':final['visual_sha256'],'candidate_collision_sha256':final['collision_sha256'],'exact_untouched_visual_triangles':proof['exact_untouched_visual_triangles'],'optical_positions_and_pbr_exact':proof['optical_positions_and_pbr_exact'],'maximum_exported_contact_vertex_distance_mm':max(v['maximum_exported_vertex_distance_mm']for v in proof['collision_vertex_checks']),'exact_port_rings':[{'source_member':r['source_member'],**r['preserved_native_port']}for r in row['members']if 'preserved_native_port'in r]})
    for row in summary['components']:
        if digest(ROOT/row['visual_glb'])!=row['visual_sha256']:raise ValueError('visual composition changed')
    result={'totals':summary['totals'],'prior_totals':summary['prior_totals'],'groups':summary['groups'],'full_glb':summary['full_glb'],'assembly':summary['assembly'],'components':components,'exact_other_visual_definitions':116-len(components),'review':review,'validation':validation,'scope':summary['scope'],'producer_sha256':{str(p.relative_to(ROOT)):digest(p)for p in [*source.glob('*.py'),ROOT/'python/cad_dense_lod.py',ROOT/'python/cad_local_lod.py',ROOT/'python/cad_glb_composition.py',ROOT/'python/test_cad_dense_lod.py']},'report_sha256':{name:digest(out/name)for name in ['summary.json','detail-summary.json','review.json','validation.json','composition.json']}}
    (source/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(result['totals'])


if __name__=='__main__':main()
