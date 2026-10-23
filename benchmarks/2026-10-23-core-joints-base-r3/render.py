"""Matched joint/base cylinder review; approved visuals are read-only."""
import json,sys,tempfile,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from build import ROOT,OUT,PREVIOUS,p,scan
import collision_review_render as raster
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review'))
f=p.module('round_joints_renderer','benchmarks/2026-10-23-visual-fidelity-review/render.py')

def main():
    r=json.loads((OUT/'verification.json').read_text());manifest=ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json'
    placement=json.loads(manifest.read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0]
    cd,cc,cn=scan.load_nodes(Path(r['source_collision']));vd,vc,vn=scan.load_nodes(Path(r['unchanged_visual']))
    visual_names={(vc[i],vd['nodes'][i]['name']):i for i in vn}
    arm={i for i in cn if cc[i]=='technology-core/arm-and-shared'}
    scopes={'arm-base':arm|{72},'whole-core':None,'base':{72},'shoulder':{5,6,7,12,13,22,53,72},
        'wrist':{i for i in range(25,57)if i not in [26,27,53,56]},'end-cover':{55}}
    paths={'installed':r['source_collision'],'current':r['previous_collision'],'expanded':r['candidate_collision'],'visual':r['unchanged_visual']};rows=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        if not helper.is_file():
            helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for scope,ids in scopes.items():
            vi=None if ids is None else {visual_names[(cc[i],cd['nodes'][i]['name'])]for i in ids}
            reference=f.load(paths['installed'],placement,ids)[0]
            for camera,direction in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
                for stage,path in paths.items():
                    data=list(f.load(path,placement,vi if stage=='visual'else ids))
                    if stage!='visual':
                        data[1][:]=[.58,.6,.63]
                        if stage=='expanded':data[1][np.isin(data[4],r['changed_nodes'])]=[.15,.64,.84]
                    target=OUT/f'{scope}-{camera}-{stage}.webp'
                    Image.fromarray(raster.raster(tuple(data),reference,direction,helper,tmp)).save(target,lossless=True)
                    rows.append(dict(scope=scope,camera=camera,stage=stage,path=str(target),sha256=scan.digest(target),direction=direction,
                        frame_bounds_m=[reference.min((0,1)).tolist(),reference.max((0,1)).tolist()]))
            print('Rendered',scope,flush=True)
    for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
    (OUT/'renders.json').write_text(json.dumps(dict(views=rows,placement=placement,placement_manifest=str(manifest),placement_manifest_sha256=scan.digest(manifest),
        note='Identical installed framing for all stages. Blue indicates new round covers and mounting-base collision. Visual file unchanged. Diagnostic flat lighting and 24-segment cylinder surfaces; actual native cylinders stay round.'),indent=2)+'\n')

if __name__=='__main__':main()
