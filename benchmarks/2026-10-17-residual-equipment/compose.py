#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Apply five disjoint residual overrides to a new complete-field inspection scene."""
import argparse, copy, json
from pathlib import Path
from audit import ROOT,module
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();baseline=ROOT/'out/rmuc2027-composed-pipeline/summary.json';original=json.loads(baseline.read_bytes());skin=json.loads((out/'final-summary.json').read_bytes());overrides={r['id']:r for r in skin['components']};rows=[]
    for prior in original['components']:
        cid=prior['id'];row=copy.deepcopy(prior);row['reference_glb']=prior['candidate_glb'];row['reference_sha256']=prior['candidate_sha256'];row['reference_triangles']=prior['candidate_triangles']
        if cid in overrides:
            change=overrides[cid];path=out/cid/'final.glb'
            if digest(path)!=change['outputs_sha256']['final.glb'] or change['source_step_sha256']!=prior['source_step_sha256'] or prior['candidate_triangles']!=change['before'] or prior['uses']!=change['uses']:raise ValueError('residual override mismatch')
            row['candidate_glb']=str(path.relative_to(ROOT));row['candidate_sha256']=digest(path);row['candidate_triangles']=change['after'];row['policy']='residual-selected-structural-lod-and-all-view-skin'
        row['placed_triangles']=row['candidate_triangles']*row['uses'];row['placed_saving']=(row['reference_triangles']-row['candidate_triangles'])*row['uses'];rows.append(row)
    summary={'schema':'rm-residual-field-composition-v1','complete':True,'components':rows,'hierarchy_sha256':original['hierarchy_sha256'],'source_sha256':original['source_sha256'],'reference_placed_triangles':sum(r['reference_triangles']*r['uses'] for r in rows),'candidate_placed_triangles':sum(r['placed_triangles'] for r in rows),'reference_summary_sha256':digest(baseline),'final_summary_sha256':digest(out/'final-summary.json'),'producer_sha256':digest(Path(__file__))}
    if summary['reference_placed_triangles']!=1573606 or summary['candidate_placed_triangles']!=skin['candidate_field_placed_triangles']:raise ValueError('field delta double counted')
    (out/'composition.json').write_text(json.dumps(summary,indent=2)+'\n')
    hp=ROOT/'out/rmuc2027-hierarchy/hierarchy.json'
    if digest(hp)!=summary['hierarchy_sha256']:raise ValueError('hierarchy changed')
    assembly=module('assembly',ROOT/'benchmarks/2026-10-17-composed-pipeline/assemble.py');results=[assembly.build(out,summary,json.loads(hp.read_bytes()),stage) for stage in ['reference','candidate']]
    result={'composition_sha256':digest(out/'composition.json'),'stages':results,'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'benchmarks/2026-10-17-composed-pipeline/assemble.py',ROOT/'python/cad_glb_composition.py']}}
    (out/'assembly.json').write_text(json.dumps(result,indent=2)+'\n');print([(r['stage'],r['placed_triangles'],r['bytes']) for r in results],flush=True)
if __name__=='__main__':main()
