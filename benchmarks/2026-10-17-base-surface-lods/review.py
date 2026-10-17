#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Matched views, per-unit collision deviations and source relief-map example."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from mesh_quality import deviation
from cad_relief_bake import bake_relief
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('base_render',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);p.add_argument('--audit',type=Path,required=True);p.add_argument('--integrity-only',action='store_true');a=p.parse_args();out=a.out;r=json.loads((out/'summary.json').read_bytes());audit=json.loads(a.audit.read_bytes());policy=json.loads((ROOT/'rules/base-surface-lods-rmuc2027.json').read_bytes());data={}
    for stage,record in r['stages'].items():
        if digest(out/stage/'geometry.npz')!=record['geometry_sha256'] or digest(out/stage/'visual.glb')!=record['visual_sha256']:raise ValueError('payload hash mismatch')
        data[stage]=render.load(out/stage/'geometry.npz')
    original=data['approved'];candidate=data['visual-lod'];collision=data['collision'];results=[];unit_checks=[];views=[]
    retained=0;light_triangles=0
    for index,unit in enumerate(audit['units']):
        before=original[2]==index;after=candidate[2]==index
        if unit['source_id'] not in policy['visual_source_units']:
            for old,new in zip(original,candidate):
                if not np.array_equal(old[before],new[after]):raise ValueError('serialized unselected source unit changed')
            retained+=1
        def lights(colours):return ((colours[:,0]>.9)&(colours[:,1]<.1))|((colours[:,1]>.9)&(colours[:,0]<.1))
        old_light=before&lights(original[1]);new_light=after&lights(candidate[1])
        for old,new in zip(original,candidate):
            if not np.array_equal(old[old_light],new[new_light]):raise ValueError('serialized light geometry/appearance/face ownership changed')
        light_triangles+=int(old_light.sum())
    for e,steps in ((15,range(12)),(45,range(0,12,3))):
        for s in steps:
            angle=math.pi*s/6;el=math.radians(e);views.append((f'e{e}-a{s*30}',(math.cos(angle)*math.cos(el),math.sin(el),math.sin(angle)*math.cos(el))))
    views.extend([('top',(0,1,.000001)),('bottom',(0,-1,.000001))])
    if '--integrity-only' in sys.argv:
        existing=json.loads((out/'validation.json').read_bytes());existing.update(serialized_unchanged_units_checked=retained,serialized_light_triangles_checked=light_triangles,producer_sha256=digest(Path(__file__)));(out/'validation.json').write_text(json.dumps(existing,indent=2)+'\n');print('Serialized integrity:',retained,'unchanged units;',light_triangles,'light triangles');return
    helper_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'
    with tempfile.TemporaryDirectory() as folder:
        tmp=Path(folder);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(helper_source),'-o',str(helper)],check=True)
        for name,view in views:
            imgs={stage:render.raster(d[0],d[1] if stage!='collision' else np.tile([.20,.65,.75],(len(d[0]),1)),original[0],view,helper,tmp,out/f'{stage}-{name}.png' if name in ('e15-a60','e15-a180','top') else None) for stage,d in data.items() if stage!='collision' or name in ('e15-a60','e15-a180','top')}
            diff=abs(imgs['approved'].astype(int)-imgs['visual-lod'].astype(int));masks=[np.any(imgs[s]!=[192,208,224],axis=2) for s in ('approved','visual-lod')];results.append({'view':name,'rgb_change_over_10_fraction':float((diff.max(2)>10).mean()),'foreground_mask_difference_fraction':float((masks[0]!=masks[1]).mean())})
            print('view',name,flush=True)
        for source in policy['visual_source_units']:
            index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source);mask=original[2]==index;reference=original[0][mask];unit_checks.append({'source_unit_id':source,'collision_sampled_deviation_mm':deviation(reference.reshape(-1,3)*1000,np.arange(reference.size//3).reshape(-1,3),collision[0][collision[2]==index].reshape(-1,3)*1000,np.arange(collision[0][collision[2]==index].size//3).reshape(-1,3),count=4096)})
            for label,view in [('front',(1,.6,1.5)),('reverse',(-1,-.6,-1.5))]:
                for stage,d in data.items():
                    select=d[2]==index;colour=d[1][select] if stage!='collision' else np.tile([.20,.65,.75],(int(select.sum()),1));render.raster(d[0][select],colour,reference,view,helper,tmp,out/f'unit-{source}-{stage}-{label}.png')
    # One source-backed 512² bake demonstrates which molded detail can become a
    # texture layer. This is not yet attached to a replacement runtime mesh.
    source=4756187;index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source);mask=original[2]==index;geometry=original[0][mask]*1000;colours=original[1][mask];normal=np.array([0.,.887010833,.461748614]);normal/=np.linalg.norm(normal);right=np.array([1.,0,0]);up=np.cross(normal,right);frame=np.array([right,up,normal]);origin=geometry.reshape(-1,3).mean(0);local=(geometry-origin)@frame.T;lo=local.min((0,1));hi=local.max((0,1));bounds=[lo[0]-1,lo[1]-1,hi[0]+1,hi[1]+1];bake=bake_relief(geometry.reshape(-1,3),np.arange(geometry.size//3).reshape(-1,3),colours,origin_mm=origin,axes=frame,bounds_uv_mm=bounds,resolution=512)
    Image.fromarray(bake['base_colour_rgba']).save(out/'backing-base-colour.png');Image.fromarray(bake['normal_rgb_linear']).save(out/'backing-normal-linear.png');np.savez_compressed(out/'backing-relief.npz',height_mm=bake['height_mm'],source_triangle_owner=bake['source_triangle_owner']);height=bake['height_mm'];valid=np.isfinite(height);scaled=np.zeros(height.shape,dtype=np.uint8);scaled[valid]=np.clip((height[valid]-height[valid].min())/max(float(np.ptp(height[valid])),1e-9)*255,0,255).astype(np.uint8);Image.fromarray(scaled).save(out/'backing-height-preview.png');(out/'backing-relief.json').write_text(json.dumps(bake['metadata'],indent=2)+'\n')
    validation={'serialized_unchanged_units_checked':retained,'serialized_light_triangles_checked':light_triangles,'visual_views':results,'maximum_rgb_change_fraction':max(x['rgb_change_over_10_fraction'] for x in results),'maximum_foreground_difference_fraction':max(x['foreground_mask_difference_fraction'] for x in results),'collision_profile_deviations':unit_checks,'relief_bake':bake['metadata'],'producer_sha256':digest(Path(__file__)),'scope':'18 sampled source-pose views and per-unit mesh distances; not a continuous geometry proof, moving-pose validation or runtime physics test.'}
    (out/'validation.json').write_text(json.dumps(validation,indent=2)+'\n');print(json.dumps({k:v for k,v in validation.items() if k not in ('visual_views','relief_bake')},indent=2))


if __name__=='__main__':main()
