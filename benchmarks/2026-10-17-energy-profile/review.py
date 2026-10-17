#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare the composed Energy Unit with profile candidates from fourteen views."""
import argparse, importlib.util, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image
from plan_cad_lods import digest, build_plan


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args(); out=a.out.resolve()
    report=json.loads((out/'summary.json').read_bytes()); loader=module('loader',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py'); raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py'); metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py')
    paths={'composed':ROOT/'out/rmuc2027-composed-pipeline/energy-unit/unit/candidate.glb'}
    paths.update({r['name']:out/(r['name']+'.glb') for r in report['candidates']})
    pose=next(n['world_matrix_mm'] for n in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes'] if n['component_id']=='energy-unit/unit')
    rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])@np.array(pose)[:3,:3]
    data={stage:loader.load(path) for stage,path in paths.items()}; data={stage:(g@rotation.T,c) for stage,(g,c,u) in data.items()}
    views=[]
    for el,azs in [(15,range(0,360,45)),(45,range(0,360,90))]:
        for az in azs:
            e,z=map(math.radians,[el,az]); views.append((f'e{el}-a{az}',(math.cos(z)*math.cos(e),math.sin(e),math.sin(z)*math.cos(e))))
    views += [('top',(0,1,.000001)),('bottom',(0,-1,.000001))]; checks=[]; folder=out/'review'; folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory); helper=tmp/'raster'; subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for name,view in views:
            images={stage:raster.raster(g,c,data['composed'][0],view,helper,tmp,folder/(stage+'-'+name+'.png')) for stage,(g,c) in data.items()}
            sheet=Image.new('RGB',(3*600,600))
            for i,stage in enumerate(paths):sheet.paste(Image.fromarray(images[stage]).resize((600,600),Image.Resampling.LANCZOS),(i*600,0))
            sheet.save(folder/(name+'.webp'),lossless=True,method=4)
            for stage in paths:
                if stage!='composed': checks.append({'stage':stage,'view':name,**metrics.metric(images['composed'],images[stage])})
    result={'views':checks,'maximum_foreground_difference':{stage:max(c['foreground_difference_relative_fraction'] for c in checks if c['stage']==stage) for stage in paths if stage!='composed'},'candidate_summary_sha256':digest(out/'summary.json'),'producer_sha256':digest(Path(__file__))}
    (out/'review.json').write_text(json.dumps(result,indent=2)+'\n'); print(result['maximum_foreground_difference'])

if __name__=='__main__':main()
