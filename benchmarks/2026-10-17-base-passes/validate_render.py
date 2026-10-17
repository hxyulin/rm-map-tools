#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check unchanged Base units exactly and compare source-pose candidate renders."""
import argparse,hashlib,json,math,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from plan_cad_lods import digest


def load(path):
    d=np.load(path,allow_pickle=False);return d['positions_mm'][d['triangles']]/1000,d['triangle_srgb'],d['unit_ids'],d['source_face_ids']


def raster(geometry,colours,reference,view,helper,tmp,target=None):
    width=height=1200;forward=np.asarray(view,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward)
    if np.linalg.norm(right)<1e-6:right=np.array([1.,0,0])
    right/=np.linalg.norm(right);up=np.cross(forward,right);frame=np.column_stack((right,up,forward));p=geometry@frame;bounds=reference@frame;lo,hi=bounds.min((0,1)),bounds.max((0,1));p-=(lo+hi)/2;scale=min((width-60)/max(hi[0]-lo[0],1e-9),(height-60)/max(hi[1]-lo[1],1e-9));p[:,:,0]=p[:,:,0]*scale+width/2;p[:,:,1]=-p[:,:,1]*scale+height/2
    normals=np.cross(geometry[:,1]-geometry[:,0],geometry[:,2]-geometry[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-20);light=forward+.8*up-.3*right;light/=np.linalg.norm(light);rgb=np.clip(colours*(.55+.45*abs(normals@light))[:,None]*255,0,255).astype('uint8');records=np.empty(len(geometry),dtype=[('p','<f4',(3,3)),('c','u1',(3,))]);records['p']=p;records['c']=rgb
    with (tmp/'input.bin').open('wb') as f:f.write(struct.pack('<iii',width,height,len(geometry)));f.write(records.tobytes())
    subprocess.run([str(helper),str(tmp/'input.bin'),str(tmp/'image.ppm'),str(tmp/'owners.bin')],check=True)
    image=np.asarray(Image.open(tmp/'image.ppm')).copy()
    if target:Image.fromarray(image).save(target)
    return image


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('review',type=Path);p.add_argument('--source-audit',type=Path,required=True);a=p.parse_args();r=json.loads((a.review/'summary.json').read_bytes());audit=json.loads(a.source_audit.read_bytes());baseline=load(a.review/'baseline/geometry.npz');source_indices={u['source_id']:i for i,u in enumerate(audit['units'])}
    checks={};cache={'baseline':baseline}
    def h(parts):
        x=hashlib.sha256()
        for part in parts:x.update(np.ascontiguousarray(part).tobytes())
        return x.hexdigest()
    for stage,spec in r['stages'].items():
        if digest(a.review/stage/'geometry.npz')!=spec['geometry_sha256'] or digest(a.review/stage/'visual.glb')!=spec['visual_sha256']:raise ValueError('candidate payload changed')
        data=load(a.review/stage/'geometry.npz');cache[stage]=data;protected=0
        for source,index in source_indices.items():
            if source in spec['changed_source_units'] or source in spec['removed_source_units']:continue
            old=baseline[2]==index;new=data[2]==index
            if h([baseline[0][old],baseline[1][old],baseline[3][old]])!=h([data[0][new],data[1][new],data[3][new]]):raise ValueError('protected original unit geometry/appearance changed')
            protected+=1
        if len(data[0])!=spec['definition_triangles']:raise ValueError('candidate triangle accounting mismatch')
        checks[stage]={'byte_exact_original_units':protected,'triangle_accounting_verified':True}
    cases=['native-detail-lod','small-hardware-lod','smooth-bores','combined'];views=[]
    for elevation,steps in ((15,range(12)),(45,range(0,12,3))):
        for step in steps:
            t=math.pi*step/6;e=math.radians(elevation);views.append((f'e{elevation}-a{step*30}',(math.cos(t)*math.cos(e),math.sin(e),math.sin(t)*math.cos(e))))
    views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))]);results={case:[] for case in cases}
    helper_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(helper_source),'-o',str(helper)],check=True)
        for name,view in views:
            original=raster(baseline[0],baseline[1],baseline[0],view,helper,tmp,a.review/f'baseline-{name}.png' if name in ('e15-a60','e15-a180','top') else None)
            oldmask=np.any(original!=[192,208,224],axis=2)
            for case in cases:
                data=cache[case];image=raster(data[0],data[1],baseline[0],view,helper,tmp,a.review/f'{case}-{name}.png' if name in ('e15-a60','e15-a180','top') else None);diff=abs(image.astype(int)-original.astype(int));mask=np.any(image!=[192,208,224],axis=2)
                metrics={'view':name,'changed_pixels_over_10_fraction':float(np.mean(diff.max(2)>10)),'foreground_mask_difference_fraction':float(np.mean(mask!=oldmask)),'mean_absolute_rgb_255':float(diff.mean())};results[case].append(metrics)
                if case=='combined' and name=='e15-a60':Image.fromarray(np.clip(diff*6,0,255).astype('uint8')).save(a.review/'combined-difference-x6.png')
            print('Compared view',name,flush=True)
        for source in (4268930,4527988,4617749):
            select=baseline[2]==source_indices[source];reference=baseline[0][select]
            raster(reference,baseline[1][select],reference,(1,.6,1.5),helper,tmp,a.review/f'unit-{source}-baseline.png')
            for case in cases:
                data=cache[case];select=data[2]==source_indices[source];raster(data[0][select],data[1][select],reference,(1,.6,1.5),helper,tmp,a.review/f'unit-{source}-{case}.png')
    summary={case:{'views':rows,'max_changed_pixels_over_10_fraction':max(row['changed_pixels_over_10_fraction'] for row in rows),'max_foreground_mask_difference_fraction':max(row['foreground_mask_difference_fraction'] for row in rows)} for case,rows in results.items()}
    result={'per_stage_integrity':checks,'render_comparisons':summary,'view_policy':'18 two-sided orthographic source-pose views, fixed source framing, 1200² pixels. RGB changes include faceting/shading; foreground differences also include newly filled bore openings. Not all moving Base poses.',
            'review_guard':{'maximum_foreground_mask_difference_fraction':.002,'maximum_rgb_changed_pixel_fraction':.02},'producer_sha256':digest(Path(__file__)),'raster_sha256':digest(helper_source)}
    for case,spec in summary.items():
        spec['passes_source_pose_render_guard']=spec['max_foreground_mask_difference_fraction']<=.002 and spec['max_changed_pixels_over_10_fraction']<=.02
    (a.review/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:{k:v for k,v in value.items() if k!='views'} for key,value in summary.items()},indent=2))
if __name__=='__main__':main()
