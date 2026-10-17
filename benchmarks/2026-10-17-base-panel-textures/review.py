#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render GLB UVs and embedded colour textures, plus source diagnostic colours."""
import argparse,io,importlib.util,json,math,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from gltf_scene import read_glb,accessor
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');metrics=importlib.util.module_from_spec(spec);spec.loader.exec_module(metrics)


def load(path):
    doc,blob=read_glb(path);g=[];cc=[];uv=[];tex=[];ids=[];texture=np.zeros((1,1,3),np.uint8)
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        source_id=node['extras']['source_unit_id']
        for prim in doc['meshes'][node['mesh']]['primitives']:
            p=accessor(doc,blob,prim['attributes']['POSITION']);t=accessor(doc,blob,prim['indices']).reshape(-1,3);g.append(p[t]);material=doc['materials'][prim['material']];textured='baseColorTexture' in material['pbrMetallicRoughness'];ids.extend([source_id]*len(t));tex.extend([textured]*len(t))
            if textured:
                image=doc['images'][doc['textures'][material['pbrMetallicRoughness']['baseColorTexture']['index']]['source']];view=doc['bufferViews'][image['bufferView']];texture=np.asarray(Image.open(io.BytesIO(blob[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']])).convert('RGB')).copy();uv.append(accessor(doc,blob,prim['attributes']['TEXCOORD_0'])[t]);cc.extend([[1,1,1]]*len(t))
            else:uv.append(np.zeros((len(t),3,2)));cc.extend([material['extras']['step_colour_srgb']]*len(t))
    return np.concatenate(g).astype(float),np.array(cc),np.concatenate(uv),np.array(tex,np.int32),np.array(ids),texture


def raster(data,reference,view,helper,tmp,target):
    g,colours,uv,tex,_,texture=data;width=height=1200;forward=np.asarray(view,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward)
    if np.linalg.norm(right)<1e-6:right=np.array([1.,0,0])
    right/=np.linalg.norm(right);up=np.cross(forward,right);frame=np.column_stack((right,up,forward));p=g@frame;bounds=reference@frame;lo,hi=bounds.min((0,1)),bounds.max((0,1));p-=(lo+hi)/2;scale=min((width-60)/max(hi[0]-lo[0],1e-9),(height-60)/max(hi[1]-lo[1],1e-9));p[:,:,0]=p[:,:,0]*scale+width/2;p[:,:,1]=-p[:,:,1]*scale+height/2;normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-20);light=forward+.8*up-.3*right;light/=np.linalg.norm(light);shade=.55+.45*abs(normal@light);rgb=np.clip(colours*shade[:,None]*255,0,255).astype('uint8');records=np.empty(len(g),dtype=[('p','<f4',(3,3)),('c','u1',(3,)),('uv','<f4',(3,2)),('textured','<i4'),('shade','<f4')]);records['p']=p;records['c']=rgb;records['uv']=uv;records['textured']=tex;records['shade']=shade
    with (tmp/'input.bin').open('wb') as f:f.write(struct.pack('<iiiii',width,height,len(g),texture.shape[1],texture.shape[0]));f.write(texture.tobytes());f.write(records.tobytes())
    subprocess.run([str(helper),str(tmp/'input.bin'),str(tmp/'image.ppm'),str(tmp/'owners.bin')],check=True);image=np.asarray(Image.open(tmp/'image.ppm')).copy();Image.fromarray(image).save(target);return image


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);paths={'before':ROOT/'out/rmuc2027-base-shells-final/base-visual.glb','panels':ROOT/'out/rmuc2027-base-panels-final/base-visual.glb','texture':ROOT/'out/rmuc2027-base-textures-final/base-visual.glb'};data={k:load(p) for k,p in paths.items()};base=data['before'];views=[]
    for el,steps in [(15,range(12)),(45,range(0,12,3))]:
        for s in steps:
            az=s*math.pi/6;e=math.radians(el);views.append((f'e{el}-a{s*30}',(math.cos(az)*math.cos(e),math.sin(e),math.sin(az)*math.cos(e))))
    views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))]);report={'whole':[],'members':[],'inputs_sha256':{k:digest(p) for k,p in paths.items()},'scope':'1200² two-sided source-pose orthographic diagnostics; UV base colour sampled bilinearly, no PBR or mip/anisotropic simulation.'}
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3','-std=c++17',str(Path(__file__).with_name('texture-raster.cpp')),'-o',str(helper)],check=True)
        for name,view in views:
            imgs={stage:raster(d,base[0],view,helper,tmp,a.out/f'whole-{stage}-{name}.png') for stage,d in data.items()}
            for stage in ['panels','texture']:report['whole'].append({'stage':stage,'view':name,**metrics.metric(imgs['before'],imgs[stage])})
        for source_id in [4268930,4527988]:
            parts={stage:tuple(x[d[4]==source_id] for x in d[:5])+(d[5],) for stage,d in data.items()};reference=parts['before'][0]
            for name,view in [('oblique',(1,.6,1.5)),('reverse',(-1,.6,-1.5)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('top',(0,1,.000001)),('bottom',(0,-1,.000001))]:
                imgs={stage:raster(d,reference,view,helper,tmp,a.out/f'member-{source_id}-{stage}-{name}.png') for stage,d in parts.items()}
                for stage in ['panels','texture']:report['members'].append({'source_unit_id':source_id,'stage':stage,'view':name,**metrics.metric(imgs['before'],imgs[stage])})
        # Crop camera to the actual UV quad while retaining the full housing as
        # occluder; this exposes text orientation and edge filtering directly.
        patch=np.load(ROOT/'out/rmuc2027-base-logo-texture/patch.npz');reference=patch['positions_mm'][patch['triangles']]/1000
        for name,view in [('normal',(0,.258819,.965926)),('oblique',(.65,.258819,.965926))]:
            for stage,d in data.items():raster(d,reference,view,helper,tmp,a.out/f'logo-{stage}-{name}.png')
    report['producer_sha256']={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),Path(__file__).with_name('texture-raster.cpp')]};(a.out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    for stage in ['panels','texture']:
        rows=[r for r in report['whole'] if r['stage']==stage];print(stage,'max silhouette',max(r['foreground_difference_relative_fraction'] for r in rows),'RGB',max(r['rgb_changed_over_10_fraction'] for r in rows),flush=True)
if __name__=='__main__':main()
