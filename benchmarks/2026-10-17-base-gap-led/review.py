#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Whole Base and isolated light silhouettes against the approved reference."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('base_render',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)


def lights(c):return ((c[:,0]>.9)&(c[:,1]<.1))|((c[:,1]>.9)&(c[:,0]<.1))


def metric(before,after):
    old=np.any(before!=[192,208,224],axis=2);new=np.any(after!=[192,208,224],axis=2)
    return {'changed_rgb_fraction':float((np.max(abs(before.astype(int)-after.astype(int)),axis=2)>10).mean()),'mask_difference_fraction':float((old!=new).mean()),'mask_difference_relative_to_reference_foreground':float((old!=new).sum()/max(1,old.sum())),'foreground_before_pixels':int(old.sum()),'foreground_after_pixels':int(new.sum())}


def main():
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument('out',type=Path);arg.add_argument('--reference',type=Path,required=True);arg.add_argument('--audit',type=Path,required=True);a=arg.parse_args();out=a.out;r=json.loads((out/'summary.json').read_bytes());ref=json.loads((a.reference/'summary.json').read_bytes());audit=json.loads(a.audit.read_bytes());data={}
    for stage,name in [('before','visual-lod'),('collision-before','collision')]:
        path=a.reference/name/'geometry.npz'
        if digest(path)!=ref['stages'][name]['geometry_sha256']:raise ValueError('reference mismatch')
        data[stage]=render.load(path)
    for stage in ('visual','collision'):
        if digest(out/stage/'geometry.npz')!=r['stages'][stage]['geometry_sha256'] or digest(out/stage/'visual.glb')!=r['stages'][stage]['visual_sha256']:raise ValueError('candidate mismatch')
        data[stage]=render.load(out/stage/'geometry.npz')
    original=data['before'];candidate=data['visual'];views=[];whole=[];led_rows=[];closeups=[]
    # Every source-unit material value remains one of that same unit's values.
    for index,u in enumerate(audit['units']):
        old=original[2]==index;new=candidate[2]==index
        if not np.array_equal(np.unique(original[1][old],axis=0),np.unique(candidate[1][new],axis=0)):raise ValueError('source-unit material palette changed')
    for e,steps in ((15,range(12)),(45,range(0,12,3))):
        for s in steps:
            angle=math.pi*s/6;el=math.radians(e);views.append((f'e{e}-a{s*30}',(math.cos(angle)*math.cos(el),math.sin(el),math.sin(angle)*math.cos(el))))
    views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))]);helper_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(helper_source),'-o',str(helper)],check=True)
        for name,view in views:
            images={stage:render.raster(d[0],np.tile([.2,.65,.75],(len(d[0]),1)) if stage.startswith('collision') else d[1],original[0],view,helper,tmp,out/f'{stage}-{name}.png' if name in ('e15-a60','e15-a180','top') else None) for stage,d in data.items() if not stage.startswith('collision') or name in ('e15-a60','e15-a180','top')};whole.append({'view':name,**metric(images['before'],images['visual'])})
            masks={}
            for stage in ('before','visual'):
                d=data[stage];mask=lights(d[1]);masks[stage]=render.raster(d[0][mask],d[1][mask],original[0],view,helper,tmp,out/f'led-{stage}-{name}.png' if name in ('e15-a60','e15-a180') else None)
            led_rows.append({'view':name,**metric(masks['before'],masks['visual'])});print('review',name,flush=True)
        selected=[4268930,4527988,4392221,4314593,4353403,4756187,4099408,4561335,4072376,4599538]
        for source in selected:
            index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source);reference=original[0][original[2]==index]
            for stage in ('before','visual','collision-before','collision'):
                d=data[stage];mask=d[2]==index
                if not mask.any():continue
                c=np.tile([.2,.65,.75],(int(mask.sum()),1)) if stage.startswith('collision') else d[1][mask];render.raster(d[0][mask],c,reference,(1,.6,1.5),helper,tmp,out/f'unit-{source}-{stage}.png')
            light_mask=(original[2]==index)&lights(original[1])
            if light_mask.any():
                reference=original[0][light_mask];imgs={}
                for stage in ('before','visual'):
                    d=data[stage];mask=(d[2]==index)&lights(d[1]);imgs[stage]=render.raster(d[0][mask],d[1][mask],reference,(1,.6,1.5),helper,tmp,out/f'light-unit-{source}-{stage}.png')
                closeups.append({'source_unit_id':source,**metric(imgs['before'],imgs['visual'])})
    validation={'whole_views':whole,'isolated_led_views':led_rows,'isolated_led_closeups':closeups,'source_unit_palettes_unchanged':True,'maximum_whole_rgb_fraction':max(x['changed_rgb_fraction'] for x in whole),'maximum_whole_mask_fraction':max(x['mask_difference_fraction'] for x in whole),'maximum_led_mask_fraction':max(x['mask_difference_fraction'] for x in led_rows),'maximum_led_closeup_mask_relative_fraction':max(x['mask_difference_relative_to_reference_foreground'] for x in closeups),'scope':'Fixed source-pose 1200² diagnostic raster comparisons; isolated LED geometry included. Not moving-pose or runtime dynamics validation.','producer_sha256':digest(Path(__file__))};(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');print(json.dumps({k:v for k,v in validation.items() if not isinstance(v,list)},indent=2))


if __name__=='__main__':main()
