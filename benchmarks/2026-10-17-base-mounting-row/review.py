#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Matched close-up and assembled comparisons for the selected mounting row."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('render',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;summary=json.loads((out/'summary.json').read_bytes());base=render.load(ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz');before=render.load(ROOT/'out/rmuc2027-base-structure-audit/4268930/trial.npz');after=render.load(out/'geometry.npz');i=int(before[2][0]);keep=base[2]!=i
    if digest(out/'geometry.npz')!=summary['geometry_sha256']:raise ValueError('candidate changed')
    reference_report=json.loads((ROOT/'out/rmuc2027-base-structure-audit/trial-summary.json').read_bytes());reference_record=next(r for r in reference_report['trials'] if r['source_unit_id']==summary['source_unit_id'])
    if digest(ROOT/'out/rmuc2027-base-structure-audit/4268930/trial.npz')!=reference_record['geometry_sha256']:raise ValueError('reference changed')
    whole={stage:[np.concatenate([x[keep],y]) for x,y in zip(base,d)] for stage,d in [('before',before),('after',after)]};report={'isolated':[],'whole':[],'scope':'1200² two-sided orthographic fixed-source-pose diagnostics. Closure changes small surface recesses intentionally; not runtime PBR or moving-pose equivalence.'}
    def metric(old,new):
        fg0=np.any(old!=[192,208,224],axis=2);fg1=np.any(new!=[192,208,224],axis=2);return {'rgb_changed_over_10_fraction':float((np.max(abs(old.astype(int)-new.astype(int)),axis=2)>10).mean()),'foreground_difference_relative_fraction':float((fg0!=fg1).sum()/max(1,fg0.sum()))}
    helper_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(helper_source),'-o',str(helper)],check=True)
        for name,view in {'oblique':(1,.6,1.5),'reverse':(-1,.6,-1.5),'top':(0,1,.000001),'bottom':(0,-1,.000001),'front':(0,.000001,1),'back':(0,.000001,-1),'mouth':(0,.88701083318,.46174861323)}.items():
            imgs=[render.raster(d[0],d[1],before[0],view,helper,tmp,out/f'{stage}-{name}.png') for stage,d in [('before',before),('after',after)]];report['isolated'].append({'view':name,**metric(*imgs)})
        views=[]
        for el,steps in ((15,range(12)),(45,range(0,12,3))):
            for s in steps:
                az=s*math.pi/6;e=math.radians(el);views.append((f'e{el}-a{s*30}',(math.cos(az)*math.cos(e),math.sin(e),math.sin(az)*math.cos(e))))
        views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))])
        for name,view in views:
            imgs=[render.raster(d[0],d[1],whole['before'][0],view,helper,tmp,out/f'whole-{stage}-{name}.png' if name in ('e15-a60','e15-a180','top','bottom') else None) for stage,d in whole.items()];report['whole'].append({'view':name,**metric(*imgs)})
    report['max_whole_rgb_changed_fraction']=max(x['rgb_changed_over_10_fraction'] for x in report['whole']);report['max_whole_foreground_difference_relative_fraction']=max(x['foreground_difference_relative_fraction'] for x in report['whole']);report['producer_sha256']=digest(Path(__file__));(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)},indent=2))
if __name__=='__main__':main()
