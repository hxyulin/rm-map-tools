#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare the micro-detail, structural LOD and fitted-cap visual stages."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from common import ROOT,module,read_mesh
import numpy as np
from PIL import Image
from cad_radial_profile import clip_below
from plan_cad_lods import digest


def cap_view(path):
    d=read_mesh(path);p,t,m,u=[d[k]for k in ['positions_mm','triangles','material_ids','unit_ids']];palette=np.array([[float(v)for v in c.split(',')]if c else[.6275]*3 for c in d['palette']]);mask=(u==1)&(abs(palette[m]-[.1333,.2902,.7451]).max(1)<.00001)&(p[t].mean(1)[:,0]<0);return p[t[mask]]@np.array([[1,0,0],[0,0,1],[0,-1,0]]).T/1000,palette[m[mask]]


def cutaway(parts):
    center=(parts['reference'][0].min((0,1))[0]+parts['reference'][0].max((0,1))[0])/2;result={}
    for stage,(g,c)in parts.items():
        p=g.reshape(-1,3);t=np.arange(len(p)).reshape(-1,3);q,f,k,_=clip_below(p*1000,t,np.arange(len(t)),axis=0,height_mm=center*1000);result[stage]=(q[f]/1000,c[k])
    return result


def light_masks(image):
    """Primary red/green visible areas, including occlusion by opaque bezels."""
    rgb=image.astype(float);red=(rgb[:,:,0]>40)&(rgb[:,:,0]>2*rgb[:,:,1]+10)&(rgb[:,:,0]>2*rgb[:,:,2]+10);green=(rgb[:,:,1]>40)&(rgb[:,:,1]>2*rgb[:,:,0]+10)&(rgb[:,:,1]>2*rgb[:,:,2]+10)
    return {'red':red,'green':green}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());prior=json.loads((ROOT/'out/rmuc2027-dart-outpost/summary.json').read_bytes());old={r['id']:r for r in prior['components']};now={r['id']:r for r in summary['components']};details=json.loads((out/'detail-summary.json').read_bytes());load=module('load',ROOT/'benchmarks/2026-10-17-game-lods/review.py').load;scene=module('scene',ROOT/'benchmarks/2026-10-17-composed-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py').raster;metric=module('metric',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py').metric;cases=[];data={};owners={}
    for stage,path in [('reference',ROOT/'out/rmuc2027-dart-outpost/candidate-field.glb'),('candidate',out/'candidate-field.glb')]:data[stage],owners[stage]=scene.load_scene(path)
    for group in ['dart-station','outpost']:
        first=next(v for v in owners['reference'].values()if v['component_id'].startswith(group+'/'));g=data['reference'][0][data['reference'][4]==first['index']];anchor=(g.min((0,1))+g.max((0,1)))/2;cases.append((group+' / complete','visual',{s:scene.select(d,owners[s],group,anchor)[:2]for s,d in data.items()}))
    del data,owners
    for row in details['components']:
        cid=row['id'];folder=out/cid;parts={'reference':load(ROOT/old[cid]['visual_glb']),'micro':load(folder/'micro.glb'),'candidate':load(folder/'visual.glb')};cases.append((cid,'visual',parts))
        if cid in ['dart-station/frame','outpost/fixed/column-cluster']:cases.append((cid+' / cutaway','visual',cutaway(parts)))
        if cid in ['dart-station/frame','dart-station/deck-and-shared-hardware','dart-station/door-candidate','outpost/fixed/upper-cluster','outpost/fixed/lower-cluster','outpost/fixed/column-cluster','outpost/rotor/module-0','dart-station/guide-rails']:
            contact={'reference':load(ROOT/old[cid]['collision_glb']),'candidate':load(ROOT/now[cid]['collision_glb'])};contact={s:(g,np.tile([.45,.65,.80],(len(g),1)))for s,(g,c)in contact.items()};cases.append((cid+' / contact','collision',contact))
    cid='dart-station/frame';cases.append(('Dart engraved end cap / close-up','profile',{'reference':cap_view(ROOT/old[cid]['visual_glb']),'candidate':cap_view(out/cid/'visual.glb')}))
    views=[('oblique',(1,.7,1.5)),('reverse',(-1,.7,-1.5)),('top',(0,1,.000001)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('bottom',(0,-1,.000001)),('side',(1,.000001,0))];entries=[]
    with tempfile.TemporaryDirectory()as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for index,(cid,kind,parts)in enumerate(cases):
            folder=out/'review'/str(index);folder.mkdir(parents=True,exist_ok=True);checks=[]
            for name,view in views:
                frames={s:raster(g,c,parts['reference'][0],view,helper,tmp,tmp/(s+'.png'))for s,(g,c)in parts.items()}
                for stage,image in frames.items():
                    if stage=='reference':continue
                    lights={}
                    if cid=='outpost / complete':
                        first=light_masks(frames['reference']);second=light_masks(image)
                        for key in first:
                            changed=int((first[key]^second[key]).sum());lights[key]={'reference_pixels':int(first[key].sum()),'candidate_pixels':int(second[key].sum()),'changed_pixels':changed}
                    sheet=Image.new('RGB',(1200,600));sheet.paste(Image.fromarray(frames['reference']).resize((600,600),Image.Resampling.LANCZOS),(0,0));sheet.paste(Image.fromarray(image).resize((600,600),Image.Resampling.LANCZOS),(600,0));sheet.save(folder/(stage+'-'+name+'.webp'),lossless=True);checks.append({'view':name,'stage':stage,**metric(frames['reference'],image),'primary_light_masks':lights})
            entries.append({'id':cid,'kind':kind,'stages':[s for s in parts if s!='reference'],'images':str(folder.relative_to(out)),'triangles':{s:len(g)for s,(g,c)in parts.items()},'views':checks});print('reviewed',cid,flush=True)
    (out/'review.json').write_text(json.dumps({'entries':entries,'summary_sha256':digest(out/'summary.json'),'detail_summary_sha256':digest(out/'detail-summary.json'),'producer_sha256':digest(__file__),'scope':'Seven matched 1200-square two-sided source-color views. Compare micro-detail omission separately from final LOD/profile fit. Full equipment, cutaways, contact meshes and one end cap. Engraved branding intentionally removed; not runtime PBR/animation validation.'},indent=2)+'\n')


if __name__=='__main__':main()
