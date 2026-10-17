#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Select shell skins plus the clean native-profile Tech Core plate override."""
import argparse,copy,json,shutil
from pathlib import Path
from audit import ROOT
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();skin=json.loads((out/'skin-summary.json').read_bytes());results=[]
    for prior in skin['components']:
        row=copy.deepcopy(prior);cid=row['id'];folder=out/cid;stage='profile' if cid=='technology-core/tool-head' else 'skin'
        proof=json.loads((folder/'profile.json').read_bytes()) if stage=='profile' else row
        if stage=='profile' and (not proof['valid_solid'] or proof['source_step_sha256']!=row['source_step_sha256'] or proof['skin_npz_sha256']!=row['outputs_sha256']['skin.npz']):raise ValueError('unqualified clean plate override')
        for suffix in ['.npz','.glb']:
            path=folder/(stage+suffix)
            if digest(path)!=proof['outputs_sha256'][stage+suffix]:raise ValueError('selected final output changed')
            shutil.copyfile(path,folder/('final'+suffix))
        row['selected_stage']=stage
        if stage=='profile':row['after']=proof['component_triangles'];row['profile_proof_sha256']=digest(folder/'profile.json')
        row['outputs_sha256']={name:digest(folder/name) for name in ['final.glb','final.npz']};results.append(row)
    report={'components':results,'skin_summary_sha256':digest(out/'skin-summary.json'),'placed_saving':sum((r['before']-r['after'])*r['uses'] for r in results),'producer_sha256':digest(Path(__file__)),'scope':'Select full-sphere skin candidates; Tech Core copper plate overrides the speckled LOD trial with a native projected-profile prism. Optical/unselected geometry retained. Rear plate relief intentionally simplified. No source, collision or runtime replacement.'};report['candidate_field_placed_triangles']=1573606-report['placed_saving'];(out/'final-summary.json').write_text(json.dumps(report,indent=2)+'\n');print('FINAL',report['placed_saving'],report['candidate_field_placed_triangles'],flush=True)
if __name__=='__main__':main()
