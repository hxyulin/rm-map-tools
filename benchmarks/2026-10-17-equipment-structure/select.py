#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Select the tested Dart LOD and the Outpost colour-margin refinement."""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from plan_cad_lods import digest

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--base',type=Path,required=True);ap.add_argument('--margin',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    summaries={p:json.loads((p/'summary.json').read_bytes()) for p in [a.base,a.margin]};reviews={p:json.loads((p/'validation.json').read_bytes()) for p in summaries};parts=[];checks=[]
    for cid,folder in [('dart-station/frame',a.base),('outpost/fixed/upper-cluster',a.margin)]:
        change=next(c for c in summaries[folder]['components'] if c['id']==cid);baseline=next(c for c in summaries[a.base]['components'] if c['id']==cid);review=next(c for c in reviews[folder]['components'] if c['id']==cid);group=cid.split('/')[0]
        if change['source_step_sha256']!=baseline['source_step_sha256'] or change['approved_glb_sha256']!=baseline['approved_glb_sha256'] or review['exported_native_sampled_deviation_mm']['max']>3.001:raise ValueError('unmatched or unqualified refinement')
        if reviews[folder]['input_summary_sha256']!=digest(folder/'summary.json'):raise ValueError('review does not match candidate')
        for name,sha in change['outputs_sha256'].items():
            if digest(folder/cid/name)!=sha:raise ValueError('selected output changed')
        destination=a.out/cid;destination.mkdir(parents=True)
        for name in change['outputs_sha256']:shutil.copy2(folder/cid/name,destination/name)
        for stage in ['before','after']:
            name=group+'-'+stage+'.glb'
            if digest(folder/name)!=review['whole_glb_sha256'][stage]:raise ValueError('complete product changed')
            shutil.copy2(folder/name,a.out/name)
        shutil.copytree(folder/'review'/group,a.out/'review'/group);parts.append(change);checks.append(review)
    summary={'components':parts,'source_ledger_sha256':summaries[a.base]['source_ledger_sha256'],'selection':'Dart initial candidate; Outpost 3 mm colour proximity margin','source_summaries_sha256':{str(p):digest(p/'summary.json') for p in summaries},'producer_sha256':digest(Path(__file__))};(a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    saving=sum(c['placed_saving'] for c in checks);validation={'components':checks,'previous_field_placed_triangles':3805082,'placed_triangle_saving':saving,'candidate_field_placed_triangles':3805082-saving,'input_summary_sha256':digest(a.out/'summary.json'),'source_reviews_sha256':{str(p):digest(p/'validation.json') for p in summaries},'producer_sha256':digest(Path(__file__))};(a.out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');shutil.copy2(a.base/'native-audit.json',a.out/'native-audit.json');print('selected placed savings',saving,'field',3805082-saving)

if __name__=='__main__':main()
