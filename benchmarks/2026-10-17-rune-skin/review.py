#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verify source-triangle subsets and compare front/side/rear visual skins."""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from run import module
from cad_visibility_skin import hemisphere_views
from export_field_package import GlbWriter
from plan_cad_lods import build_plan,digest


def colour_metrics(a,b,metrics):
    result=metrics.metric(a,b)
    for name,channel in [('red',0),('blue',2)]:
        others=[i for i in range(3) if i!=channel];x=(a[:,:,channel]>80)&(a[:,:,others[0]]<30)&(a[:,:,others[1]]<30);y=(b[:,:,channel]>80)&(b[:,:,others[0]]<30)&(b[:,:,others[1]]<30)
        result[name]={'before_pixels':int(x.sum()),'after_pixels':int(y.sum()),'lost_pixels':int((x&~y).sum()),'gained_pixels':int((y&~x).sum()),'difference_relative_fraction':float((x!=y).sum()/max(1,x.sum()))}
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());prior=ROOT/summary.get('reference_directory','out/rmuc2027-rune-detail')
    structural=module('structural',ROOT/'benchmarks/2026-10-17-equipment-structure/review.py');loader=module('loader',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py')
    poses={}
    for n in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes']:
        if n['component_id']:poses.setdefault(n['component_id'],np.array(n['world_matrix_mm']))
    rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])@poses[summary['components'][0]['id']][:3,:3];display=np.eye(4);display[:3,:3]=rotation;pieces={'before':[],'after':[]};selected={};checks=[];fronts={}
    for change in summary['components']:
        cid=change['id'];old=prior/cid/'candidate';new=out/cid/'candidate'
        if digest(old.with_suffix('.npz'))!=change['reference_npz_sha256'] or digest(new.with_suffix('.glb'))!=change['outputs_sha256']['candidate.glb']:raise ValueError('input changed')
        before=np.load(old.with_suffix('.npz'));after=np.load(new.with_suffix('.npz'));indices=np.load(out/cid/'retained-triangle-indices.npy')
        generated=change.get('generated_unit_ids',np.unique(after['unit_ids'][after['unit_ids']<0]).tolist());original=~np.isin(after['unit_ids'],generated)
        if len(indices)!=int(original.sum()) or not np.array_equal(before['positions_mm'][before['triangles'][indices]],after['positions_mm'][after['triangles'][original]]) or not np.array_equal(before['material_ids'][indices],after['material_ids'][original]) or not np.array_equal(before['unit_ids'][indices],after['unit_ids'][original]):raise ValueError('not exact source triangle subset')
        cap_check=None
        if (~original).any() and change.get('flat_back'):
            proof=change['flat_back'];front=np.asarray(proof['front_direction']);geometry=after['positions_mm'][after['triangles'][~original]];maximum=float(abs(geometry@front-proof['rear_offset_mm']).max());normals=np.cross(geometry[:,1]-geometry[:,0],geometry[:,2]-geometry[:,0])
            if maximum>1e-5 or (normals@front>1e-7).any() or int((~original).sum())!=change['cap_triangles']:raise ValueError('rear cap plane/orientation/count mismatch')
            cap_check={'maximum_planarity_mm':maximum,'outward_rear_orientation':True,'triangles':change['cap_triangles']}
        front_checks=[]
        for surface in change.get('derived_fronts',[]):
            ids=after['unit_ids']==surface['unit_id'];g=after['positions_mm'][after['triangles'][ids]];normal=np.asarray(surface['front_direction']);maximum=float(abs(g@normal-surface['plane_offset_mm']).max());cross=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0])
            if maximum>1e-5 or (cross@normal< -1e-7).any() or not np.all(after['material_ids'][ids]==surface['material_id']):raise ValueError('derived front plane/orientation/material mismatch')
            front_checks.append({'unit_id':surface['unit_id'],'triangles':int(ids.sum()),'maximum_planarity_mm':maximum,'outward_front_orientation':True,'source_material_preserved':True})
        b=structural.payload(old.with_suffix('.glb'));c=structural.payload(new.with_suffix('.glb'))
        for unit,parts in c.items():
            if unit in generated:continue
            for key,(data,colour,count) in parts.items():
                if unit not in b or key not in b[unit] or not np.isin(data,b[unit][key][0]).all():raise ValueError('export changed retained position/normal/material attributes')
        checks.append({'id':cid,'retained_triangles_exact_positions_normals_materials_units':len(indices),'removed_triangles':len(before['triangles'])-len(indices),'derived_cap_triangles':int((~original).sum()),'flat_rear_check':cap_check,'flat_front_checks':front_checks})
        if 'front_direction' in change['selection']:fronts[cid.split('/')[2]]=rotation@np.asarray(change['selection']['front_direction'])
        for stage,path in [('before',old),('after',new)]:
            data=loader.load(path.with_suffix('.glb'));data=(data[0]@rotation.T,data[1],data[2]);pieces[stage].append(data)
            if cid.endswith('arm-0') or cid.endswith('hub-cluster'):selected.setdefault(cid.replace('/','-'),{'front':fronts[cid.split('/')[2]]})[stage]=data
    whole={stage:tuple(np.concatenate([p[k] for p in rows]) for k in range(3)) for stage,rows in pieces.items()}
    for bank,front in fronts.items():selected['whole-'+bank]={**whole,'front':front}
    for stage in ['before','after']:
        writer=GlbWriter('Rune '+stage,{'version':'2.0','copyright':'DJI / RoboMaster source geometry and appearance; user-approved native-profile inspection candidate'})
        for change in summary['components']:
            cid=change['id'];path=(prior/cid/'candidate.npz') if stage=='before' else out/cid/'candidate.npz';d=np.load(path);palette=[v or None for v in d['palette'].tolist()]
            for unit in np.unique(d['unit_ids']):
                ids=d['unit_ids']==unit;used,inv=np.unique(d['triangles'][ids],return_inverse=True);writer.add_node(cid+'/shell-'+str(unit),d['positions_mm'][used]/1000,inv.reshape(-1,3),[palette[k] for k in d['material_ids'][ids]],matrix=display,extras={'component_id':cid,'native_shell_index':int(unit),'inspection_only':True,'derived_geometry':bool(unit<0),'flat_back_visual_skin':change.get('flat_back') is not None and stage=='after'})
        writer.write(out/('rune-'+stage+'.glb'))
    tests=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for scope,versions in selected.items():
            front=versions['front'];novel=hemisphere_views(front,angles_deg=(45,70),azimuth_count=4);views=[('front',front)]+[(f'front-angle-{i}',v) for i,v in enumerate(novel[1:])]+[('rear',-front)];images=out/'review'/scope;images.mkdir(parents=True,exist_ok=True)
            for name,view in views:
                frames={stage:raster.raster(versions[stage][0],versions[stage][1],versions['before'][0],view,helper,tmp,images/(stage+'-'+name+'.png')) for stage in ['before','after']};tests.append({'scope':scope,'view':name,**colour_metrics(frames['before'],frames['after'],metrics)})
            print('reviewed',scope,flush=True)
    complete=len(summary['components'])==13
    report={'before':summary['before'],'after':summary['after'],'saving':summary['before']-summary['after'],'original_rune_triangles':478828 if complete else None,'cumulative_rune_saving':478828-summary['after'] if complete else None,'candidate_composed_field_triangles':2669054-478828+summary['after'] if complete else None,'checks':checks,'views':tests,'producer_sha256':digest(Path(__file__)),'scope':'Exact retained source-triangle and exported attribute subset; separately bound derived panels checked for plane/orientation/material. Matched source-pose views include independent 45/70 degree front views and rear checks. Raster selection/validation are finite, no all-view proof, collision, PBR or animation certification.'};(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['checks','views']},indent=2))
if __name__=='__main__':main()
