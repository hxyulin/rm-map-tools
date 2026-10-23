"""Whole head, cutaway and rear support comparisons with unchanged visuals."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from survey import ROOT,OUT,p,f,raster

def main():
    survey=json.loads((OUT/'survey.json').read_text());d,c,n=p.scan.load_nodes(Path(survey['source']));head={i for i in n if c[i]=='technology-core/tool-head'}
    scopes={'head':head,'cutaway':head-{108,82,1266,1268,1254,1255,1262,1263},'rear-support':{1668},'whole-core':None}
    dirs={r['camera']:r['direction']for r in survey['views']};dirs={k:dirs[k]for k in ['front','back','left']}
    records=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        for variant in json.loads((OUT/'variants.json').read_text()):
            report_path=Path(variant['path']);r=json.loads(report_path.read_text());out=report_path.parent;omitted={x['node']for x in r['omitted_collision_owners']}
            # Visual selection uses source native shell identity within component.
            vd,vc,vn=p.scan.load_nodes(Path(r['unchanged_visual']));vmap={(vc[i],vd['nodes'][i]['name']):i for i in vn}
            for scope,ids in scopes.items():
                reference=f.load(r['approved_collision'],survey['placement'],ids)[0]
                if scope=='rear-support':
                    # Box corners can project beyond the curved source envelope.
                    # Use one common union frame for every side of this close-up.
                    reference=np.concatenate([reference,f.load(r['candidate_collision'],survey['placement'],{1668})[0]])
                vi=None if ids is None else {vmap[(c[i],d['nodes'][i]['name'])]for i in ids}
                for camera,direction in dirs.items():
                    for stage,path in [('current',r['approved_collision']),('candidate',r['candidate_collision']),('visual',r['unchanged_visual'])]:
                        selected=vi if stage=='visual'else (ids-omitted if ids is not None and stage=='candidate'else ids)
                        data=list(f.load(path,survey['placement'],selected))
                        if stage!='visual':
                            data[1][:]=[.58,.6,.63]
                            if stage=='current':data[1][np.isin(data[4],list(omitted))]=[.9,.51,.2]
                            else:data[1][data[4]==1668]=[.15,.64,.84]
                        target=out/f'{scope}-{camera}-{stage}.webp'
                        Image.fromarray(raster.raster(tuple(data),reference,direction,helper,tmp)).save(target,lossless=True)
                        records.append(dict(variant=r['variant'],scope=scope,camera=camera,stage=stage,path=str(target),sha256=p.scan.digest(target),direction=direction,
                            frame_bounds_m=[reference.min((0,1)).tolist(),reference.max((0,1)).tolist()]))
                print('Rendered',r['variant'],scope,flush=True)
    (OUT/'renders.json').write_text(json.dumps(dict(views=records,note='Orange current surfaces are compact collision details omitted by the candidate; blue is the new seven-box rear support. All visual bytes unchanged. Identical cameras/framing; flat diagnostic lighting.'),indent=2)+'\n')

if __name__=='__main__':main()
