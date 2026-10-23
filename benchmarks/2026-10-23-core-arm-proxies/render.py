"""Matched installed/candidate arm images in the real source placement frame."""
import json,subprocess,tempfile,sys
from pathlib import Path
import numpy as np
from PIL import Image
from build import ROOT,OUT,module,scan
import collision_review_render as raster
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review'))
f=module('arm_source_renderer','benchmarks/2026-10-23-visual-fidelity-review/render.py')

def main():
    report=json.loads((OUT/'verification.json').read_text())
    manifest=ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json'
    placement=json.loads(manifest.read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0]
    ref=json.loads(scan.REF.read_text());rows=[];visibility=[]
    arm={role:{r['node']for r in ref['targets']['core-arm'][role]['nodes']}for role in ['visual','collision']}
    scopes={'arm':arm,'whole-core':{'visual':None,'collision':None},
        'upper-tube':{'visual':{15},'collision':{17}},'lower-tube':{'visual':{24},'collision':{26}},
        'shoulder':{'visual':{3},'collision':{5}},'elbow':{'visual':{16},'collision':{18}},
        'upper-joint':{'visual':{20},'collision':{22}},'wrist':{'visual':{23},'collision':{25}}}
    changed={'visual':{15,24},'collision':{5,17,18,22,25,26}}
    native=ROOT/'out/rmuc2027-equipment-pipeline/technology-core/arm-and-shared/native.glb'
    meta=json.loads(native.with_name('native.json').read_text());assert scan.digest(native)==meta['native_glb_sha256']
    assert scan.digest(native.with_name('source.step'))==meta['source_step_sha256']
    reference=f.load(report['sources']['visual'],placement,arm['visual'])
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        if not helper.is_file():
            helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for scope,selection in scopes.items():
            for camera,direction in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
                for role in ['visual','collision']:
                    source=report['sources'][role];target=report[f'{role}_candidate'];ids=selection[role]
                    before=f.load(source,placement,ids);after=f.load(target,placement,ids)
                    focus=before[0];protected={};pixels_by_stage={}
                    for stage,data in [('installed',before),('candidate',after)]:
                        data=list(data)
                        if role=='collision':
                            data[1][:]=[.58,.6,.63]
                            if stage=='candidate':data[1][np.isin(data[4],list(changed[role]))]=[.15,.64,.84]
                        path=OUT/f'{scope}-{camera}-{role}-{stage}.webp'
                        pixels=raster.raster(tuple(data),focus,direction,helper,tmp)
                        Image.fromarray(pixels).save(path,lossless=True)
                        rows.append(dict(scope=scope,camera=camera,role=role,stage=stage,path=str(path),sha256=scan.digest(path),
                            direction=direction,source_frame_bounds_m=[focus.min((0,1)).tolist(),focus.max((0,1)).tolist()]))
                        if scope=='whole-core'and role=='visual':
                            tri=np.fromfile(tmp/'owners.bin',dtype='<i4').reshape(1800,1800);valid=tri>=0;node=np.full(tri.shape,-1,np.int32);node[valid]=data[4][tri[valid]]
                            protected[stage]=np.isin(node,report['protected_visual_nodes']);pixels_by_stage[stage]=pixels
                    if protected:
                        old=protected['installed'];new=protected['candidate'];common=old&new
                        delta=abs(pixels_by_stage['installed'].astype(int)-pixels_by_stage['candidate'].astype(int)).max(2)
                        visibility.append(dict(camera=camera,source_protected_pixels=int(old.sum()),lost_protected_pixels=int((old&~new).sum()),
                            gained_protected_pixels=int((new&~old).sum()),common_protected_rgb_changes_over_1=int((common&(delta>1)).sum())))
                if scope=='arm':
                    data=f.load(native,placement);path=OUT/f'arm-{camera}-visual-step.webp'
                    Image.fromarray(raster.raster(data,reference[0],direction,helper,tmp)).save(path,lossless=True)
                    rows.append(dict(scope=scope,camera=camera,role='visual',stage='step',path=str(path),sha256=scan.digest(path),
                        direction=direction,source_frame_bounds_m=[reference[0].min((0,1)).tolist(),reference[0].max((0,1)).tolist()]))
            print('Rendered',scope,flush=True)
    for p,h in report['input_pins'].items():assert scan.digest(Path(p))==h
    output=dict(views=rows,protected_visibility=visibility,source_arm_native_glb=str(native),source_arm_native_sha256=scan.digest(native),
        source_arm_native_triangles=meta['native_triangles'],placement=placement,placement_manifest=str(manifest),placement_manifest_sha256=scan.digest(manifest),
        caveat='Identical cameras and source framing. Flat two-sided source colors, not simulator PBR or emission. Rest pose only; no dynamic contact validation.')
    (OUT/'renders.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Visibility',visibility,flush=True)

if __name__=='__main__':main()
