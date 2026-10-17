#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Sample Base visibility, normalized reuse candidates and native cost hotspots.

Pixel visibility at a single source pose never certifies hidden/removable faces.
"""
import argparse,hashlib,json,math,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image,ImageDraw
from cad_document import CadDocument
from audit_body_symmetry import FrameFingerprints,frame_of
from plan_cad_lods import digest


def raster(triangles,colours,view,target,helper,tmp,width=1200,height=1200):
    forward=np.asarray(view,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward)
    if np.linalg.norm(right)<1e-5:right=np.array([1.,0,0])
    right/=np.linalg.norm(right);up=np.cross(forward,right)
    projected=triangles@np.column_stack((right,up,forward));lo,hi=projected.min((0,1)),projected.max((0,1));projected-=(lo+hi)/2
    scale=min((width-60)/max(hi[0]-lo[0],1e-9),(height-60)/max(hi[1]-lo[1],1e-9))
    projected[:,:,0]=projected[:,:,0]*scale+width/2;projected[:,:,1]=-projected[:,:,1]*scale+height/2
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-20)
    light=forward+.8*up-.3*right;light/=np.linalg.norm(light)
    # Work in source sRGB consistently with other diagnostic renderers.
    rgb=np.clip(colours*(.55+.45*np.abs(normal@light))[:,None]*255,0,255).astype('uint8')
    records=np.empty(len(triangles),dtype=[('p','<f4',(3,3)),('c','u1',(3,))]);records['p']=projected;records['c']=rgb
    with (tmp/'input.bin').open('wb') as stream:stream.write(struct.pack('<iii',width,height,len(triangles)));stream.write(records.tobytes())
    subprocess.run([str(helper),str(tmp/'input.bin'),str(tmp/'render.ppm'),str(tmp/'owners.bin')],check=True)
    owners=np.fromfile(tmp/'owners.bin',dtype='<i4').reshape(height,width);visible=np.unique(owners[owners>=0])
    if target:Image.open(tmp/'render.ppm').save(target)
    return visible


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('audit',type=Path);a=p.parse_args();out=a.audit
    report=json.loads((out/'audit.json').read_bytes())
    for name in ('geometry.npz','source.step'):
        if digest(out/name)!=report['outputs_sha256'][name]:raise ValueError('audit input checksum mismatch')
    data=np.load(out/'geometry.npz',allow_pickle=False);p=data['positions_mm']/1000;t=data['triangles'];geometry=p[t];unit_ids=data['unit_ids'];face_ids=data['source_face_ids'];rgb=data['source_srgb'][data['colour_indices']]
    units=report['units'];groups=defaultdict(list);no_frame=[]
    with CadDocument.from_step(out/'source.step',workers=1,intern_layers=True) as cad:
        for i,u in enumerate(units):
            frame=frame_of(cad.index,cad.index.r(u['source_id']))
            if frame is None:no_frame.append(u['source_id']);continue
            fp=FrameFingerprints(cad.index,frame);groups[fp.signature(cad.index.r(u['source_id']))].append(i)
        cad.verify_source()
    matches=[]
    for indices in groups.values():
        if len(indices)<2:continue
        matches.append({'units':[units[i]['source_id'] for i in indices],'count':len(indices),
                        'triangle_uses':sum(units[i]['triangles'] for i in indices),
                        'candidate_redundant_triangle_storage':sum(units[i]['triangles'] for i in indices[1:])})
    matches.sort(key=lambda g:g['candidate_redundant_triangle_storage'],reverse=True)
    print('Normalized reuse candidates:',len(matches),'groups',flush=True)
    seen=np.zeros(len(t),dtype=np.uint16);view_results=[]
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(Path(__file__).with_name('visibility-raster.cpp')),'-o',str(helper)],check=True)
        # A front/back overlap and clear foreground triangle exercise z ownership.
        sample=np.array([[[0,0,0],[1,0,0],[0,1,0]],[[0,0,1],[1,0,1],[0,1,1]]],float)
        visible=raster(sample,np.ones((2,3)),(0,0,1),None,helper,tmp,width=64,height=64)
        if list(visible)!=[1]:raise ValueError('visibility raster depth-order regression')
        for elevation in (15,45):
            for step in range(12):
                angle=step*math.pi/6;e=math.radians(elevation);view=(math.cos(angle)*math.cos(e),math.sin(e),math.sin(angle)*math.cos(e))
                target=out/f'view-{elevation}-{step}.png' if step in (0,2,4,6,8,10) and elevation==15 else None
                visible=raster(geometry,rgb,view,target,helper,tmp,width=1600,height=1600);seen[visible]+=1
                view_results.append({'elevation_deg':elevation,'azimuth_deg':step*30,'observed_triangles':len(visible)})
                print('Visibility',elevation,step,len(visible),flush=True)
        for y,name in ((1,'top'),(-1,'bottom')):
            visible=raster(geometry,rgb,(0,y,.000001),out/f'view-{name}.png',helper,tmp,width=1600,height=1600);seen[visible]+=1;view_results.append({'view':name,'observed_triangles':len(visible)})
        # Inspect heavy source units in isolation; IDs are geometry identities,
        # not guessed functional assignments. No unit is deleted or regrouped.
        ordered=sorted(range(len(units)),key=lambda i:units[i]['triangles'],reverse=True)[:12]
        sheet=Image.new('RGB',(1600,4*380),'#f2f4f7');draw=ImageDraw.Draw(sheet)
        for tile,i in enumerate(ordered):
            select=unit_ids==i;image=out/f'unit-{units[i]["source_id"]}.png';raster(geometry[select],rgb[select],(1,.6,1.5),image,helper,tmp,width=780,height=560)
            panel=Image.open(image);panel.thumbnail((510,335));x=(tile%3)*533;y=(tile//3)*380;sheet.paste(panel,(x,y+30));draw.text((x+8,y+5),f'#{units[i]["source_id"]}  {units[i]["triangles"]:,} triangles',fill='#17202f',font_size=19)
        sheet.save(out/'heavy-units.png')
    unit_stats=[]
    for i,u in enumerate(units):
        select=unit_ids==i;visible=int(np.count_nonzero(seen[select]));span=np.array(u['bbox_mm'][1])-u['bbox_mm'][0]
        unit_stats.append({'source_id':u['source_id'],'kind':u['kind'],'triangles':u['triangles'],'faces':u['faces'],'max_span_mm':float(span.max()),'observed_in_external_views':visible,'not_observed_in_external_views':u['triangles']-visible})
    costs_by_span={}
    for bound in (20,50,100,200):
        selected=[u for u in unit_stats if u['max_span_mm']<=bound];costs_by_span[str(bound)]={'units':len(selected),'triangles':sum(u['triangles'] for u in selected)}
    face_visibility=[]
    for source in np.unique(face_ids):
        mask=face_ids==source;face_visibility.append({'source_face_id':int(source),'triangles':int(mask.sum()),'observed':int(np.count_nonzero(seen[mask]))})
    np.savez(out/'visibility.npz',observed_views_per_triangle=seen)
    result={'source_sha256':report['source_sha256'],'component_step_sha256':report['component_step_sha256'],'audit_sha256':digest(out/'audit.json'),
            'definition_triangles':len(t),'ever_observed_triangles':int(np.count_nonzero(seen)),'not_observed_triangles':int(np.count_nonzero(seen==0)),
            'views':view_results,'visibility_resolution_px':1600,'visibility_scope':'26 two-sided orthographic exterior views at the single source pose, including top and bottom. Never-observed triangles may be occluded, edge-on or subpixel. This does not authorize deletion or cover open/moving Base poses.',
            'units':unit_stats,'cost_by_max_unit_span_mm':costs_by_span,'face_visibility':face_visibility,
            'normalized_reuse_candidates':matches,'units_without_explicit_frame':no_frame,
            'reuse_scope':'Quantized source-graph fingerprints in per-unit frames (1e-5 mm points, 1e-9 directions). Candidate discovery only; incidence, complete appearance and transformed geometry equivalence not certified. Sharing storage does not remove placed triangles.',
            'producer_sha256':{f.name:digest(f) for f in [Path(__file__),Path(__file__).with_name('visibility-raster.cpp')]},'original_geometry_unchanged':True}
    (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('units','face_visibility','normalized_reuse_candidates','views','units_without_explicit_frame')},indent=2))
if __name__=='__main__':main()
