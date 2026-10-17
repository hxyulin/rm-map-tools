#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Inspect adaptive housing LOD with approved lights and top crossbar composed."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from plan_cad_lods import digest
from scipy.spatial import cKDTree
spec=importlib.util.spec_from_file_location('render',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;report=json.loads((out/'summary.json').read_bytes());path=ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz'
    if digest(path)!=report['reference_geometry_sha256'] or digest(out/'geometry.npz')!=report['geometry_sha256']:raise ValueError('input changed')
    base=render.load(path);bar=render.load(ROOT/'out/rmuc2027-base-top-mounting-row-final/geometry.npz');keep=base[2]!=bar[2][0];base=[np.concatenate([x[keep],y]) for x,y in zip(base,bar)];after=render.load(out/'geometry.npz');index=int(after[2][0]);mask=base[2]==index;before=[x[mask] for x in base];keep=~mask;whole_after=[np.concatenate([x[keep],y]) for x,y in zip(base,after)];validation={'isolated':[],'whole':[],'scope':'Matched 1200² two-sided orthographic source-pose diagnostics against approved housing, with approved light primitives and top crossbar composed. Not runtime PBR, all moving poses or contact equivalence.'}
    native=np.load(ROOT/'out/rmuc2027-base-surface-lods-v3/approved/geometry.npz');nt=native['triangles'][native['unit_ids']==index];used=np.unique(nt);positions=native['positions_mm'][used];locked=np.unique(np.concatenate([np.asarray(region['locked_source_vertex_indices'],dtype=np.int64) for region in report['lod']['regions']]));tree=cKDTree(positions[locked]) if len(locked) else None
    protected=tree.query(after[0].reshape(-1,3)*1000)[0].reshape(-1,3).min(1)<.001 if tree is not None else np.zeros(len(after[0]),bool)
    def metric(old,new):
        fg0=np.any(old!=[192,208,224],axis=2);fg1=np.any(new!=[192,208,224],axis=2);return {'rgb_changed_over_10_fraction':float((np.max(abs(old.astype(int)-new.astype(int)),axis=2)>10).mean()),'foreground_difference_relative_fraction':float((fg0!=fg1).sum()/max(1,fg0.sum())),'mean_absolute_rgb_255':float(abs(old.astype(int)-new.astype(int)).mean())}
    helper_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(helper_source),'-o',str(helper)],check=True)
        for name,view in {'oblique':(1,.6,1.5),'reverse':(-1,.6,-1.5),'top':(0,1,.000001),'bottom':(0,-1,.000001),'front':(0,.000001,1),'back':(0,.000001,-1),'end':(1,.000001,0)}.items():
            images={stage:render.raster(d[0],d[1],before[0],view,helper,tmp,out/f'{stage}-{name}.png') for stage,d in [('before',before),('after',after)]};validation['isolated'].append({'view':name,**metric(images['before'],images['after'])})
            if name in ('oblique','reverse','top'):
                colors=np.where(protected[:,None],[.95,.34,.12],[.18,.65,.7]);render.raster(after[0],colors,before[0],view,helper,tmp,out/f'locks-{name}.png');diff=np.clip(abs(images['before'].astype(int)-images['after'].astype(int))*6,0,255).astype('uint8');Image.fromarray(diff).save(out/f'diff-{name}.png')
        views=[]
        for el,steps in ((15,range(12)),(45,range(0,12,3))):
            for s in steps:
                az=s*math.pi/6;e=math.radians(el);views.append((f'e{el}-a{s*30}',(math.cos(az)*math.cos(e),math.sin(e),math.sin(az)*math.cos(e))))
        views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))])
        for name,view in views:
            imgs=[render.raster(d[0],d[1],base[0],view,helper,tmp,out/f'whole-{stage}-{name}.png' if name in ('e15-a60','e15-a180','top','bottom') else None) for stage,d in [('before',base),('after',whole_after)]];validation['whole'].append({'view':name,**metric(*imgs)})
    validation['max_whole_rgb_changed_fraction']=max(x['rgb_changed_over_10_fraction'] for x in validation['whole']);validation['max_whole_foreground_difference_relative_fraction']=max(x['foreground_difference_relative_fraction'] for x in validation['whole']);validation['locked_source_vertex_count']=len(locked);validation['producer_sha256']=digest(Path(__file__));(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');print(json.dumps({k:v for k,v in validation.items() if not isinstance(v,list)},indent=2))
if __name__=='__main__':main()
