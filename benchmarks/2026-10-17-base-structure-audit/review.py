#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare isolated and assembled bore-cap trials in matched diagnostic views."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image,ImageDraw
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('render',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)
VIEWS={'oblique':(1,.6,1.5),'reverse':(-1,.6,-1.5),'top':(0,1,.000001),'bottom':(0,-1,.000001),'front':(0,.000001,1),'back':(0,.000001,-1),'end':(1,.000001,0)}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;summary=json.loads((out/'trial-summary.json').read_bytes());base=render.load(ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz');report={'isolated':[],'assembled':[],'assembled_trial_units':[],'scope':'Matched two-sided orthographic 1200² diagnostic raster; no runtime PBR, changing pose or continuous visibility proof.'};whole=[x.copy() for x in base]
    helper_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(helper_source),'-o',str(helper)],check=True)
        for trial in summary['trials']:
            source=trial['source_unit_id'];folder=out/str(source);path=folder/'trial.npz'
            if digest(path)!=trial['geometry_sha256']:raise ValueError('trial changed')
            data=render.load(path);i=int(data[2][0]);mask=base[2]==i;reference=base[0][mask]
            if len(data[0])<len(reference):
                keep=whole[2]!=i;whole=[np.concatenate([x[keep],y]) for x,y in zip(whole,data)];report['assembled_trial_units'].append(source)
            for name,view in VIEWS.items():
                imgs=[]
                for label,geometry,colours in [('current',reference,base[1][mask]),('trial',data[0],data[1])]:
                    imgs.append(render.raster(geometry,colours,reference,view,helper,tmp,folder/f'{label}-{name}.png'))
                old,new=imgs;fg0=np.any(old!=[192,208,224],axis=2);fg1=np.any(new!=[192,208,224],axis=2);report['isolated'].append({'source_unit_id':source,'view':name,'rgb_changed_over_10_fraction':float((np.max(abs(old.astype(int)-new.astype(int)),axis=2)>10).mean()),'foreground_difference_relative_fraction':float((fg0!=fg1).sum()/max(1,fg0.sum()))})
                if name in ('oblique','bottom'):
                    support=np.load(folder/'support-classification.npz')['on_source_plane']
                    render.raster(reference,np.where(support[:,None],[.18,.64,.63],[.94,.44,.14]),reference,view,helper,tmp,folder/f'support-{name}.png')
                    # Raster ownership provides depth-tested edge overlays.
                    render.raster(reference,base[1][mask],reference,view,helper,tmp)
                    owner=np.fromfile(tmp/'owners.bin',dtype='<i4').reshape(1200,1200);edge=np.zeros_like(owner,dtype=bool)
                    edge[1:]|=(owner[1:]!=owner[:-1])&(owner[1:]>=0);edge[:,1:]|=(owner[:,1:]!=owner[:,:-1])&(owner[:,1:]>=0)
                    wire=old.copy();wire[edge]=[235,145,50];Image.fromarray(wire).save(folder/f'wire-{name}.png')
            print('reviewed',source,flush=True)
        views=[]
        for el,steps in ((15,range(12)),(45,range(0,12,3))):
            for s in steps:
                az=s*math.pi/6;e=math.radians(el);views.append((f'e{el}-a{s*30}',(math.cos(az)*math.cos(e),math.sin(e),math.sin(az)*math.cos(e))))
        views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))])
        for name,view in views:
            images=[render.raster(d[0],d[1],base[0],view,helper,tmp,out/f'{label}-{name}.png' if name in ('e15-a60','e15-a180','top','bottom') else None) for label,d in [('current',base),('trial',whole)]];old,new=images;fg0=np.any(old!=[192,208,224],axis=2);fg1=np.any(new!=[192,208,224],axis=2);report['assembled'].append({'view':name,'rgb_changed_over_10_fraction':float((np.max(abs(old.astype(int)-new.astype(int)),axis=2)>10).mean()),'foreground_difference_relative_fraction':float((fg0!=fg1).sum()/max(1,fg0.sum()))})
    report['max_assembled_rgb_changed_fraction']=max(x['rgb_changed_over_10_fraction'] for x in report['assembled']);report['max_assembled_foreground_difference_relative_fraction']=max(x['foreground_difference_relative_fraction'] for x in report['assembled']);report['producer_sha256']=digest(Path(__file__));report['raster_sha256']=digest(helper_source);(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)},indent=2))
if __name__=='__main__':main()
