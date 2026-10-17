#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Assembly-aware light images with normals matching the exported green optic."""
import argparse,json,math,shutil,struct,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image,ImageDraw
from plan_cad_lods import digest
from gltf_scene import read_glb,accessor


def load(path):
    d=np.load(path);tri=d['positions_mm'][d['triangles']]/1000;c=d['triangle_srgb'];norm=d['triangle_vertex_normals'] if 'triangle_vertex_normals' in d else None
    if norm is None:
        n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-30);norm=np.repeat(n[:,None,:],3,axis=1)
    return tri,c,norm,d['unit_ids']


def raster(data,reference,view,helper,tmp,target):
    tri,c,norm,_=data;w=h=1200;forward=np.asarray(view,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward)
    if np.linalg.norm(right)<1e-6:right=np.array([1.,0,0])
    right/=np.linalg.norm(right);up=np.cross(forward,right);frame=np.column_stack((right,up,forward));p=tri@frame;bounds=reference@frame;lo,hi=bounds.min((0,1)),bounds.max((0,1));p-=(lo+hi)/2;scale=min((w-60)/max(hi[0]-lo[0],1e-9),(h-60)/max(hi[1]-lo[1],1e-9));p[:,:,0]=p[:,:,0]*scale+w/2;p[:,:,1]=-p[:,:,1]*scale+h/2;light=forward+.8*up-.3*right;light/=np.linalg.norm(light);records=np.empty(len(tri),dtype=[('p','<f4',(3,3)),('n','<f4',(3,3)),('c','u1',(3,))]);records['p']=p;records['n']=norm;records['c']=np.rint(np.clip(c,0,1)*255).astype('uint8')
    with (tmp/'input.bin').open('wb') as f:f.write(struct.pack('<iii',w,h,len(tri)));f.write(np.asarray(light,dtype='<f4').tobytes());f.write(records.tobytes())
    subprocess.run([str(helper),str(tmp/'input.bin'),str(tmp/'image.ppm'),str(tmp/'owner.bin')],check=True);image=np.asarray(Image.open(tmp/'image.ppm')).copy();Image.fromarray(image).save(target);owner=np.fromfile(tmp/'owner.bin',dtype='<i4').reshape(h,w);material=np.zeros((h,w),dtype=np.uint8);valid=owner>=0;rgb=c[owner[valid]];material[valid]=np.where((rgb[:,0]>.9)&(rgb[:,1]<.1),1,np.where((rgb[:,1]>.9)&(rgb[:,0]<.1),2,0));return image,material


def wire_front(data,reference,axis,path):
    """Overlay front-facing optic edges, masked by the rendered green aperture."""
    tri,c,_,_=data;select=(c[:,1]>.9)&(c[:,0]<.1);tri=tri[select];forward=np.asarray(axis,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward);right/=np.linalg.norm(right);up=np.cross(forward,right);frame=np.column_stack((right,up,forward));p=tri@frame;bounds=reference@frame;lo,hi=bounds.min((0,1)),bounds.max((0,1));p-=(lo+hi)/2;scale=min(1140/(hi[0]-lo[0]),1140/(hi[1]-lo[1]));p[:,:,0]=p[:,:,0]*scale+600;p[:,:,1]=-p[:,:,1]*scale+600;image=Image.open(path).convert('RGB');overlay=image.copy();draw=ImageDraw.Draw(overlay)
    for triangle in p:
        points=[tuple(v[:2]) for v in triangle];draw.line(points+[points[0]],fill=(0,64,0),width=3)
    rgb=np.asarray(image).astype(int);mask=(rgb[:,:,1]>3*np.maximum(rgb[:,:,0],rgb[:,:,2]));Image.composite(overlay,image,Image.fromarray(mask.astype('uint8')*255)).save(path.with_name(path.stem+'-wire.png'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);p.add_argument('--reference',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--integrity-only',action='store_true');p.add_argument('--wire-only',action='store_true');a=p.parse_args();out=a.out;r=json.loads((out/'summary.json').read_bytes());audit=json.loads(a.audit.read_bytes());data={'before':load(a.reference/'visual/geometry.npz')}
    for stage,spec in r['stages'].items():
        if digest(out/stage/'geometry.npz')!=spec['geometry_sha256'] or digest(out/stage/'visual.glb')!=spec['visual_sha256']:raise ValueError('payload mismatch')
        data[stage]=load(out/stage/'geometry.npz')
    integrity={};old_arrays=np.load(a.reference/'visual/geometry.npz')
    def non_light(colours):return ~(((colours[:,0]>.9)&(colours[:,1]<.1))|((colours[:,1]>.9)&(colours[:,0]<.1)))
    old_keep=non_light(old_arrays['triangle_srgb'])
    for stage in r['stages']:
        candidate=np.load(out/stage/'geometry.npz');keep=non_light(candidate['triangle_srgb']);old_points=old_arrays['positions_mm'][old_arrays['triangles'][old_keep]];new_points=candidate['positions_mm'][candidate['triangles'][keep]]
        if not np.array_equal(old_points,new_points):raise ValueError('serialized non-light positions changed')
        for key in ('triangle_srgb','source_face_ids','unit_ids'):
            if not np.array_equal(old_arrays[key][old_keep],candidate[key][keep]):raise ValueError('serialized non-light metadata changed')
        for i in range(len(audit['units'])):
            if not np.array_equal(np.unique(old_arrays['triangle_srgb'][old_arrays['unit_ids']==i],axis=0),np.unique(candidate['triangle_srgb'][candidate['unit_ids']==i],axis=0)):raise ValueError('source-unit palette changed')
        normal_error=0.
        if stage.startswith('ico'):
            doc,binary=read_glb(out/stage/'visual.glb');center=np.asarray(r['optic']['fit']['center_mm'])
            for node in doc['nodes']:
                if node.get('extras',{}).get('source_unit_id')!=4072376:continue
                for primitive in doc['meshes'][node['mesh']]['primitives']:
                    colour=doc['materials'][primitive['material']]['extras']['step_colour_srgb']
                    if not np.allclose(colour,[.065,.981,.062],rtol=0,atol=1e-8):continue
                    p=accessor(doc,binary,primitive['attributes']['POSITION']).astype(float)*1000;normal=accessor(doc,binary,primitive['attributes']['NORMAL']);expected=p-center;expected/=np.linalg.norm(expected,axis=1)[:,None];normal_error=max(normal_error,float(abs(normal-expected).max()))
            if normal_error>1e-6:raise ValueError('exported green normals are not radial')
        integrity[stage]={'byte_exact_non_light_triangles':int(keep.sum()),'source_unit_palettes_unchanged':True,'green_radial_normal_max_error':normal_error}
    if a.wire_only:
        index=next(i for i,u in enumerate(audit['units']) if u['source_id']==4072376);reference=data['before'][0][data['before'][3]==index]
        for stage,d in data.items():wire_front(d,reference,r['optic']['aperture_axis'],out/f'{stage}-optic-front.png')
        print('Front optic wire overlays generated.');return
    if a.integrity_only:
        validation=json.loads((out/'validation.json').read_bytes());validation['serialized_integrity']=integrity;validation['producer_sha256']=digest(Path(__file__));(out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');print(json.dumps(integrity,indent=2));return
    views=[]
    for e,steps in ((15,range(12)),(45,range(0,12,3))):
        for step in steps:
            t=math.pi*step/6;el=math.radians(e);views.append((f'e{e}-a{step*30}',(math.cos(t)*math.cos(el),math.sin(el),math.sin(t)*math.cos(el)),None))
    views.extend([('top',(0,1,.00001),None),('bottom',(0,-1,.00001),None)])
    for source in (4392221,4099408,4561335,4599538):views.extend([(f'unit-{source}',(1,.6,1.5),source),(f'unit-{source}-rear',(-1,-.6,-1.5),source)])
    axis=np.array(r['optic']['aperture_axis']);views.extend([('optic-front',tuple(axis),4072376),('optic-side',tuple(axis+np.array([1.,-.2,0])),4072376),('optic-rear',tuple(-axis),4072376)])
    results={s:[] for s in r['stages']};helper_source=Path(__file__).with_name('normal-raster.cpp')
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3','-std=c++17',str(helper_source),'-o',str(helper)],check=True)
        for name,view,source in views:
            index=next((i for i,u in enumerate(audit['units']) if u['source_id']==source),None);reference=data['before'][0] if source is None else data['before'][0][data['before'][3]==index];images={}
            for stage,d in data.items():
                # Unit close-ups retain their surrounding opaque assembly, so
                # extending a quad under a neighboring shell is tested in situ.
                images[stage]=raster(d,reference,view,helper,tmp,out/f'{stage}-{name}.png')
            old,oldmat=images['before']
            for stage in r['stages']:
                image,material=images[stage];row={'view':name,'source_unit_id':source,'rgb_changed_over_10_fraction':float((abs(image.astype(int)-old.astype(int)).max(2)>10).mean()),'red_added_pixels':int(((material==1)&(oldmat!=1)).sum()),'red_removed_pixels':int(((oldmat==1)&(material!=1)).sum()),'green_added_pixels':int(((material==2)&(oldmat!=2)).sum()),'green_removed_pixels':int(((oldmat==2)&(material!=2)).sum())}
                for colour,value in [('red',1),('green',2)]:row[colour+'_reference_pixels']=int((oldmat==value).sum());row[colour+'_mask_difference_relative_fraction']=float(((material==value)!=(oldmat==value)).sum()/max(1,(oldmat==value).sum()))
                results[stage].append(row)
            print('rendered',name,flush=True)
    index=next(i for i,u in enumerate(audit['units']) if u['source_id']==4072376);reference=data['before'][0][data['before'][3]==index]
    for stage,d in data.items():wire_front(d,reference,r['optic']['aperture_axis'],out/f'{stage}-optic-front.png')
    result={'serialized_integrity':integrity,'stages':results,'scope':'18 whole-assembly source-pose views and 11 in-situ closeups; 1200² diffuse diagnostic with interpolated normals matching the export. Not runtime PBR, continuous hidden-surface proof or all moving poses.','producer_sha256':digest(Path(__file__)),'raster_sha256':digest(helper_source)};(out/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({s:{'whole_rgb_max':max(x['rgb_changed_over_10_fraction'] for x in rows if x['source_unit_id'] is None),'red_whole_relative_max':max(x['red_mask_difference_relative_fraction'] for x in rows if x['source_unit_id'] is None),'optic_front':next(x for x in rows if x['view']=='optic-front')} for s,rows in results.items()},indent=2))


if __name__=='__main__':main()
