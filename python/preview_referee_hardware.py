#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render matched source/coarse/rough hardware views and measure exported meshes.

The existing two-sided depth rasterizer supplies visibility, not a losslessness
proof or runtime PBR validation. All candidates share the source camera framing.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import numpy as np
from PIL import Image,ImageDraw
from referee_hardware import digest
from mesh_quality import deviation
from gltf_scene import read_glb,accessor

ROOT=Path(__file__).resolve().parents[1]
VIEWS={'oblique':(1,.7,1.5),'reverse':(-1,.7,-1.5),'x':(1,0,.00001),'y':(0,1,.00001),'z':(.00001,0,1)}


def verify_glb(path,expected):
    """Check actual GLB attributes, indices, bounds and declared triangle count."""
    doc,blob=read_glb(path);triangles=0;points=[]
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            p=accessor(doc,blob,primitive['attributes']['POSITION'])
            n=accessor(doc,blob,primitive['attributes']['NORMAL'])
            t=accessor(doc,blob,primitive['indices']).ravel()
            if not np.isfinite(p).all() or not np.isfinite(n).all() or len(t)%3 or t.max()>=len(p):
                raise ValueError('invalid GLB payload')
            triangles+=len(t)//3;points.append(p)
    p=np.concatenate(points)
    if triangles!=expected['triangles'] or digest(path)!=expected['sha256']:
        raise ValueError('GLB count or checksum differs from manifest')
    np.testing.assert_allclose([p.min(0),p.max(0)],expected['bounds_m'],atol=2e-8,rtol=0)
    return triangles


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path);args=parser.parse_args()
    package=args.package.resolve();manifest=json.loads((package/'manifest.json').read_text());out=package/'review';out.mkdir(exist_ok=True)
    source=ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py'
    spec=importlib.util.spec_from_file_location('hardware_depth_preview',source);raster=importlib.util.module_from_spec(spec);spec.loader.exec_module(raster)
    rows=[];canvas=Image.new('RGB',(1200,len(manifest['models'])*430),'#f6f8fb');draw=ImageDraw.Draw(canvas)
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster'
        subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for index,model in enumerate(manifest['models']):
            data={}
            for variant in ['source','coarse','rough']:
                verify_glb(package/model['outputs'][variant]['file'],model['outputs'][variant])
                d=np.load(package/(model['id']+'-'+variant+'.npz'))
                colors=np.array([[.6275]*3 if not k else list(map(float,k.split(',')))for k in d['palette']])[d['material_ids']]
                data[variant]=(d['positions_mm'],d['triangles'],colors)
            p,t,_=data['source'];reference=p[t]/1000;images={}
            for variant,(q,faces,colors) in data.items():
                for name,view in VIEWS.items():
                    target=out/(model['id']+'-'+variant+'-'+name+'.png')
                    image=raster.raster(q[faces]/1000,colors,reference,view,helper,tmp,target)
                    images[(variant,name)]=image
                col=['source','coarse','rough'].index(variant)
                canvas.paste(Image.fromarray(images[(variant,'oblique')]).resize((390,390)),(col*400,index*430+30))
                draw.text((col*400+8,index*430+10),f"{model['id']} {variant}: {len(faces):,} triangles",fill='black')
            metrics={}
            for variant in ['coarse','rough']:
                q,faces,_=data[variant]
                silhouette=[]
                for name in VIEWS:
                    a=np.any(images[('source',name)]!=[192,208,224],axis=2);b=np.any(images[(variant,name)]!=[192,208,224],axis=2)
                    silhouette.append(float(np.count_nonzero(a!=b)/max(1,np.count_nonzero(a|b))))
                metrics[variant]={'sampled_bidirectional_deviation_mm':deviation(p,t,q,faces,count=512),
                    'max_foreground_silhouette_difference_fraction':max(silhouette),'views':len(VIEWS)}
            rows.append({'id':model['id'],'outputs':model['outputs'],'review':metrics});print(model['id'],json.dumps(metrics),flush=True)
    gallery=[]
    for model in manifest['models']:
        row={k:model[k] for k in ['id','description','outputs','appearance']}
        row['images']={variant:{view:f"{model['id']}-{variant}-{view}.png" for view in VIEWS}
            for variant in ['source','coarse','rough']}
        gallery.append(row)
    template=(ROOT/'python/preview/referee_hardware.html').read_text()
    (out/'gallery.html').write_text(template.replace('__MODELS_JSON__',json.dumps(gallery).replace('<','\\u003c')))
    canvas.save(out/'overview.png')
    result={'producer_sha256':digest(__file__),'manifest_sha256':digest(package/'manifest.json'),'models':rows,
        'scope':'5 matched two-sided orthographic views, source-framed. Deterministic sampled distances are not a Hausdorff bound. Hulls intentionally fill holes/recesses. No collision or scoring validation.'}
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
