"""Collision envelope tradeoff comparisons, including exact unchanged visuals."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from build import ROOT,OUT,p,v,scan

def main():
    survey=json.loads((ROOT/'out/rmuc2027-core-head-back-trial/survey.json').read_text())
    reference_module=p.module('coarse_head_reference_render','benchmarks/2026-10-23-core-head-back-trial/survey.py');f=reference_module.f;raster=reference_module.raster
    rows=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        for item in json.loads((OUT/'variants.json').read_text()):
            path=Path(item['path']);r=json.loads(path.read_text());out=path.parent;d,c,n=scan.load_nodes(Path(r['source_collision']));head={i for i in n if c[i]=='technology-core/tool-head'}
            vd,vc,vn=scan.load_nodes(Path(r['unchanged_visual']));vm={(vc[i],vd['nodes'][i]['name']):i for i in vn}
            source_head=f.load(r['source_collision'],survey['placement'],head)[0];target_head=f.load(r['candidate_collision'],survey['placement'],set(r['kept_head_nodes'])|{1668})[0]
            for scope in ['head','whole-core']:
                ids=head if scope=='head'else None;vi={vm[(c[i],d['nodes'][i]['name'])]for i in head}if ids is not None else None
                reference=np.concatenate([source_head,target_head])if scope=='head'else f.load(r['source_collision'],survey['placement'])[0]
                for view in survey['views']:
                    camera=view['camera'];direction=view['direction']
                    for stage,model in [('accepted',r['source_collision']),('candidate',r['candidate_collision']),('visual',r['unchanged_visual'])]:
                        data=list(f.load(model,survey['placement'],vi if stage=='visual'else ids))
                        if stage!='visual':
                            data[1][:]=[.58,.6,.63]
                            if stage=='candidate':data[1][data[4]==1668]=[.16,.63,.84]if r['variant']=='balanced'else[.78,.42,.19]
                        target=out/f'{scope}-{camera}-{stage}.webp'
                        Image.fromarray(raster.raster(tuple(data),reference,direction,helper,tmp)).save(target,lossless=True)
                        rows.append(dict(variant=r['variant'],scope=scope,camera=camera,stage=stage,path=str(target),sha256=scan.digest(target),direction=direction,
                            frame_bounds_m=[reference.min((0,1)).tolist(),reference.max((0,1)).tolist()]))
                print('Rendered',r['variant'],scope,flush=True)
    (OUT/'renders.json').write_text(json.dumps(dict(views=rows,note='Blue balanced / orange lean head envelopes, grey exact retained collision. All visual bytes unchanged. Same camera and common union frame within each comparison; flat diagnostic lighting.'),indent=2)+'\n')

if __name__=='__main__':main()
