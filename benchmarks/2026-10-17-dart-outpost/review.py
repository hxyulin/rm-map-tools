#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render complete equipment, isolated subassemblies and separate contact meshes."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from run import ROOT,module
import numpy as np
from PIL import Image
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());prior=json.loads((ROOT/'out/rmuc2027-arena-budget/summary.json').read_bytes());old={r['id']:r for r in prior['components']};now={r['id']:r for r in summary['components']};detail=json.loads((out/'detail-summary.json').read_bytes());load=module('load',ROOT/'benchmarks/2026-10-17-game-lods/review.py').load;scene=module('scene',ROOT/'benchmarks/2026-10-17-composed-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py').raster;metric=module('metric',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py').metric
    cases=[];data={};owners={}
    for s,path in [('reference',ROOT/'out/rmuc2027-arena-budget/candidate-field.glb'),('candidate',out/'candidate-field.glb')]:data[s],owners[s]=scene.load_scene(path)
    for group in ['dart-station','outpost']:
        first=next(v for v in owners['reference'].values() if v['component_id'].startswith(group+'/'));g=data['reference'][0][data['reference'][4]==first['index']];anchor=(g.min((0,1))+g.max((0,1)))/2
        selected={s:scene.select(d,owners[s],group,anchor)[:2] for s,d in data.items()};cases.append((group+' / complete','visual',selected))
    del data,owners
    for row in detail['components']:
        cid=row['id'];cases.append((cid,'visual',{'reference':load(ROOT/old[cid]['visual_glb']),'candidate':load(ROOT/now[cid]['visual_glb'])}))
        if cid in ['dart-station/door-candidate','outpost/fixed/upper-cluster','outpost/fixed/lower-cluster','outpost/fixed/column-cluster','outpost/rotor/module-0']:
            parts={s:load(ROOT/r['collision_glb']) for s,r in [('reference',old[cid]),('candidate',now[cid])]};parts={s:(g,np.tile([.45,.65,.80],(len(g),1))) for s,(g,c) in parts.items()};cases.append((cid+' / contact','collision',parts))
    views=[('oblique',(1,.7,1.5)),('reverse',(-1,.7,-1.5)),('top',(0,1,.000001)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('bottom',(0,-1,.000001)),('side',(1,.000001,0))];entries=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for index,(cid,kind,parts) in enumerate(cases):
            folder=out/'review'/str(index);folder.mkdir(parents=True,exist_ok=True);checks=[]
            for name,view in views:
                frames={s:raster(g,c,parts['reference'][0],view,helper,tmp,tmp/(s+'.png')) for s,(g,c) in parts.items()};sheet=Image.new('RGB',(1200,600))
                for j,image in enumerate(frames.values()):sheet.paste(Image.fromarray(image).resize((600,600),Image.Resampling.LANCZOS),(600*j,0))
                sheet.save(folder/(name+'.webp'),lossless=True);checks.append({'view':name,**metric(frames['reference'],frames['candidate'])})
            entries.append({'id':cid,'kind':kind,'images':str(folder.relative_to(out)),'triangles':{s:len(g) for s,(g,c) in parts.items()},'views':checks});print('reviewed',cid,flush=True)
    (out/'review.json').write_text(json.dumps({'entries':entries,'summary_sha256':digest(out/'summary.json'),'producer_sha256':digest(__file__),'scope':'Seven matched 1200-square two-sided source-color diagnostic views for complete equipment and individual changed definitions. Contact meshes shown separately. Not runtime PBR, animation or a continuous silhouette certificate.'},indent=2)+'\n')


if __name__=='__main__':main()
