#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare source-pose Base skin and backing-shell candidates at matched framing."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('previous',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous);render=previous.render

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(exist_ok=True,parents=True);stages={'before':ROOT/'out/rmuc2027-base-shells-audit/baseline.npz','skins':ROOT/'out/rmuc2027-base-skins-final/geometry.npz','shells':ROOT/'out/rmuc2027-base-shells-final/geometry.npz'};data={k:render.load(v) for k,v in stages.items()};base=data['before'];audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());views=[]
    for el,steps in ((15,range(12)),(45,range(0,12,3))):
        for s in steps:
            az=s*math.pi/6;e=math.radians(el);views.append((f'e{el}-a{s*30}',(math.cos(az)*math.cos(e),math.sin(e),math.sin(az)*math.cos(e))))
    views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))]);validation={'whole':[],'members':[],'input_sha256':{k:digest(p) for k,p in stages.items()},'scope':'Matched 1200² source-pose orthographic flat diagnostic images. Not PBR, arbitrary camera position or moving-pose validation.'}
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for name,view in views:
            imgs={stage:render.raster(d[0],d[1],base[0],view,helper,tmp,a.out/f'whole-{stage}-{name}.png') for stage,d in data.items()}
            for stage in ('skins','shells'):validation['whole'].append({'stage':stage,'view':name,**previous.metric(imgs['before'],imgs[stage])})
            validation.setdefault('backing_only',[]).append({'view':name,**previous.metric(imgs['skins'],imgs['shells'])});print('whole',name,flush=True)
        for source in [4268930,4314593,4353403,4392221,4527988,4594338,4664029,4693907,4723785,4756187]:
            index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source);parts={k:[x[d[2]==index] for x in d] for k,d in data.items()};directions=[('oblique',(1,.6,1.5)),('reverse',(-1,.6,-1.5)),('top',(0,1,.000001))]
            if source==4268930:directions.extend([('bottom',(0,-1,.000001)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('end',(1,.000001,0))])
            for name,view in directions:
                imgs={stage:render.raster(d[0],d[1],parts['before'][0],view,helper,tmp,a.out/f'member-{source}-{stage}-{name}.png') for stage,d in parts.items()}
                for stage in ('skins','shells'):validation['members'].append({'source_unit_id':source,'stage':stage,'view':name,**previous.metric(imgs['before'],imgs[stage])})
            print('member',source,flush=True)
    validation['producer_sha256']=digest(Path(__file__));(a.out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    for stage in ('skins','shells'):
        rows=[x for x in validation['whole'] if x['stage']==stage];print(stage,'max silhouette',max(x['foreground_difference_relative_fraction'] for x in rows),'max RGB',max(x['rgb_changed_over_10_fraction'] for x in rows))
if __name__=='__main__':main()
