"""Matched accepted mesh versus parameter-shape diagnostic previews."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from research import ROOT,OUT,p,scan,previous

def main():
    r=json.loads((OUT/'verification.json').read_text());survey=json.loads((ROOT/'out/rmuc2027-core-head-back-trial/survey.json').read_text())
    d,c,n=scan.load_nodes(Path(r['source_collision']));head={i for i in n if c[i]=='technology-core/tool-head'}
    vd,vc,vn=scan.load_nodes(Path(r['unchanged_visual']));vmap={(vc[i],vd['nodes'][i]['name']):i for i in vn}
    scopes={'head':head,'rear-support':{1668},'backing-strips':{288,624,944,112},'one-strip':{288}}
    directions={row['camera']:row['direction']for row in survey['views']if row['camera']in ['front','back','left']};rows=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        for scope,ids in scopes.items():
            reference=previous.f.load(r['source_collision'],survey['placement'],ids)[0]
            vi={vmap[(c[i],d['nodes'][i]['name'])]for i in ids}
            for camera,direction in directions.items():
                for stage,path in [('accepted',r['source_collision']),('vectors',r['candidate_collision']),('visual',r['unchanged_visual'])]:
                    data=list(previous.f.load(path,survey['placement'],vi if stage=='visual'else ids))
                    if stage!='visual':
                        data[1][:]=[.58,.6,.63]
                        if stage=='accepted':data[1][np.isin(data[4],r['changed_head_nodes'])]=[.88,.51,.2]
                        else:
                            data[1][data[4]==1668]=[.15,.64,.84]
                            data[1][np.isin(data[4],[112,288,624,944])]=[.52,.40,.85]
                    target=OUT/f'{scope}-{camera}-{stage}.webp'
                    Image.fromarray(previous.raster.raster(tuple(data),reference,direction,helper,tmp)).save(target,lossless=True)
                    rows.append(dict(scope=scope,camera=camera,stage=stage,path=str(target),sha256=scan.digest(target),direction=direction,
                        frame_bounds_m=[reference.min((0,1)).tolist(),reference.max((0,1)).tolist()]))
            print('Rendered',scope,flush=True)
    (OUT/'renders.json').write_text(json.dumps(dict(views=rows,note='Orange selects the five source owners. Blue shows exact box primitives, purple shows fitted convex hulls. Diagnostic previews only; shapes are exported as parameter records. Matched cameras/source framing, flat lighting.'),indent=2)+'\n')

if __name__=='__main__':main()
