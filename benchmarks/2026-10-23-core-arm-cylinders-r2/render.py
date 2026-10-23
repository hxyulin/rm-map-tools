"""Installed/current/expanded collision and approved visual, matched cameras."""
import json,sys,tempfile,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
from build import ROOT,OUT,PREVIOUS,prior,scan
import collision_review_render as raster
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review'))
f=prior.module('expanded_arm_source_render','benchmarks/2026-10-23-visual-fidelity-review/render.py')

def main():
    report=json.loads((OUT/'verification.json').read_text());ref=json.loads(scan.REF.read_text())
    manifest=ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json'
    placement=json.loads(manifest.read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0]
    arm_collision={r['node']for r in ref['targets']['core-arm']['collision']['nodes']}
    arm_visual={r['node']for r in ref['targets']['core-arm']['visual']['nodes']}
    scopes={'arm':(arm_collision,arm_visual),'whole-core':(None,None),'motor-1':({30},{28}),
        'motor-2':({37},{35}),'main-tube':({17},{15}),'second-tube':({26},{24})}
    paths={'installed':report['source_collision'],'current':report['previous_collision'],'expanded':report['candidate_collision'],'visual':report['unchanged_visual']}
    rows=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        if not helper.is_file():
            helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for scope,(ci,vi)in scopes.items():
            reference=f.load(paths['installed'],placement,ci)[0]
            for camera,direction in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
                for stage,path in paths.items():
                    data=list(f.load(path,placement,vi if stage=='visual'else ci))
                    if stage!='visual':
                        data[1][:]=[.58,.6,.63]
                        if stage=='expanded':data[1][np.isin(data[4],report['changed_nodes'])]=[.15,.64,.84]
                    image=raster.raster(tuple(data),reference,direction,helper,tmp);target=OUT/f'{scope}-{camera}-{stage}.webp'
                    Image.fromarray(image).save(target,lossless=True)
                    rows.append(dict(scope=scope,camera=camera,stage=stage,path=str(target),sha256=scan.digest(target),direction=direction,
                        frame_bounds_m=[reference.min((0,1)).tolist(),reference.max((0,1)).tolist()]))
            print('Rendered',scope,flush=True)
    for p,h in report['input_pins'].items():assert scan.digest(Path(p))==h
    output=dict(views=rows,placement=placement,placement_manifest=str(manifest),placement_manifest_sha256=scan.digest(manifest),
        description='Original installed collision fixes every camera. Current is the reviewed first arm pass. Blue expanded surfaces are newly changed four owners; grey remains exact. Approved visual file is unchanged. Flat two-sided diagnostic lighting, not runtime PBR or contact validation.')
    (OUT/'renders.json').write_text(json.dumps(output,indent=2)+'\n')

if __name__=='__main__':main()
