#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Matched source-pose views and light-visibility diagnostics for aggressive Base LOD."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('render',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)

def replace(base,member):
    keep=~np.isin(base[2],np.unique(member[2]));return [np.concatenate([x[keep],y]) for x,y in zip(base,member)]

def metric(a,b):
    fg0=np.any(a!=[192,208,224],axis=2);fg1=np.any(b!=[192,208,224],axis=2);result={'rgb_changed_over_10_fraction':float((np.max(abs(a.astype(int)-b.astype(int)),axis=2)>10).mean()),'foreground_difference_relative_fraction':float((fg0!=fg1).sum()/max(1,fg0.sum()))}
    for name,channel,other in [('red',0,1),('green',1,0)]:
        x=(a[:,:,channel]>80)&(a[:,:,other]<30)&(a[:,:,2]<30);y=(b[:,:,channel]>80)&(b[:,:,other]<30)&(b[:,:,2]<30);result[name]={'before_pixels':int(x.sum()),'after_pixels':int(y.sum()),'lost_pixels':int((x&~y).sum()),'gained_pixels':int((y&~x).sum()),'difference_relative_fraction':float((x!=y).sum()/max(1,x.sum()))}
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;out.mkdir(exist_ok=True,parents=True)
    base=render.load(ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz')
    for path in ['out/rmuc2027-base-top-mounting-row-final/geometry.npz','out/rmuc2027-base-housing-local-final/geometry.npz']:base=replace(base,render.load(ROOT/path))
    after=replace(base,render.load(ROOT/'out/rmuc2027-base-housing-aggressive-sparse/geometry.npz'));body=ROOT/'out/rmuc2027-base-bodies-aggressive';report=json.loads((body/'summary.json').read_bytes());units=[4527988]
    for d in report['decisions']:
        if d['accepted']:after=replace(after,render.load(body/str(d['source_unit_id'])/'geometry.npz'));units.append(d['source_unit_id'])
    if len(base[0])!=109860 or len(after[0])!=82414:raise ValueError('composition mismatch')
    views=[]
    for el,steps in ((15,range(12)),(45,range(0,12,3))):
        for s in steps:
            az=s*math.pi/6;e=math.radians(el);views.append((f'e{el}-a{s*30}',(math.cos(az)*math.cos(e),math.sin(e),math.sin(az)*math.cos(e))))
    views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))]);validation={'whole':[],'members':[],'scope':'1200² matched two-sided flat diagnostic views in source pose. Not runtime PBR, moving poses or a continuous surface error bound.'}
    helper_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp';audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes())
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(helper_source),'-o',str(helper)],check=True)
        for name,view in views:
            imgs=[render.raster(d[0],d[1],base[0],view,helper,tmp,out/f'whole-{stage}-{name}.png') for stage,d in [('before',base),('after',after)]];validation['whole'].append({'view':name,**metric(*imgs)});print('whole',name,flush=True)
        for source_id in units:
            index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source_id);old=[x[base[2]==index] for x in base];new=[x[after[2]==index] for x in after]
            for name,view in [('oblique',(1,.6,1.5)),('reverse',(-1,.6,-1.5)),('top',(0,1,.000001))]:
                imgs=[render.raster(d[0],d[1],old[0],view,helper,tmp,out/f'member-{source_id}-{stage}-{name}.png') for stage,d in [('before',old),('after',new)]];validation['members'].append({'source_unit_id':source_id,'view':name,**metric(*imgs)})
            print('member',source_id,flush=True)
    validation['max_whole_foreground_difference_relative_fraction']=max(x['foreground_difference_relative_fraction'] for x in validation['whole']);validation['producer_sha256']=digest(Path(__file__));(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');print('max silhouette difference',validation['max_whole_foreground_difference_relative_fraction'])
if __name__=='__main__':main()
