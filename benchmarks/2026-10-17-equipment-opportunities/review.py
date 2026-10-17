#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare diagnostic tessellation and fan LOD against the approved meshes."""
import argparse,collections,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb
from mesh_quality import deviation
from plan_cad_lods import digest,build_plan

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();audit=json.loads((out/'audit.json').read_bytes());fan=json.loads((out/'fan-trial.json').read_bytes());source=ROOT/'out/rmuc2027-equipment-pipeline';loader=module('load',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');groups=collections.defaultdict(list);poses={}
    for c in audit['components']:groups[c['group']].append(c)
    for n in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes']:
        if n['component_id']:poses.setdefault(n['component_id'],np.array(n['world_matrix_mm']))
    views=[]
    for el,azs in [(15,range(0,360,45)),(45,range(0,360,90))]:
        for az in azs:
            e=math.radians(el);z=math.radians(az);views.append((f'e{el}-a{az}',(math.cos(z)*math.cos(e),math.sin(e),math.sin(z)*math.cos(e))))
    views += [('top',(0,1,.000001)),('bottom',(0,-1,.000001))];results=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for group,rows in groups.items():
            versions={'current':[],'angular':[]};qualities=[]
            for c in rows:
                current=source/c['id']/'lod.glb';trial=out/c['id']/'native-angular-trial.glb'
                if digest(current)!=c['approved_glb_sha256'] or digest(trial)!=c['native_angular_trial']['visual_sha256']:raise ValueError('audit candidate changed')
                old=loader.load(current);new=loader.load(trial)
                if len(old[0])!=c['current_triangles'] or len(new[0])!=c['native_angular_trial']['triangles']:raise ValueError('exported count differs')
                native=np.load(source/c['id']/'native.npz');g=new[0]*1000;q=deviation(native['positions_mm'],native['triangles'],g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3),count=8192);qualities.append({'id':c['id'],'exported_native_deviation_mm':q});versions['current'].append(old);versions['angular'].append(new)
            if group=='Fans':
                if digest(out/'fan-lod-trial.glb')!=fan['visual_sha256']:raise ValueError('fan candidate changed')
                f=loader.load(out/'fan-lod-trial.glb');versions['fan-lod']=[f];native=np.load(source/rows[0]['id']/'native.npz');g=f[0]*1000;quality=deviation(native['positions_mm'],native['triangles'],g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3),count=32768)
                if quality['max']>1.001 or len(f[0])!=fan['after_triangles']:raise ValueError('exported fan guard/count failed')
                original,_=read_glb(source/rows[0]['id']/'lod.glb');candidate,_=read_glb(out/'fan-lod-trial.glb')
                if original['materials']!=candidate['materials'] or candidate['materials'][0]['extras']['step_colour_srgb'] is not None:raise ValueError('fan appearance provenance changed')
                qualities.append({'id':'fan/body-2717086','stage':'fan-lod','exported_native_deviation_mm':quality})
            rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])@poses[rows[0]['id']][:3,:3];data={stage:tuple(np.concatenate([v[k] for v in values]) for k in range(3)) for stage,values in versions.items()};data={stage:(v[0]@rotation.T,v[1],v[2]) for stage,v in data.items()};images=out/'review'/group;images.mkdir(parents=True,exist_ok=True);checks=[]
            for name,view in views:
                frames={stage:raster.raster(v[0],v[1],data['current'][0],view,helper,tmp,images/(stage+'-'+name+'.png')) for stage,v in data.items()}
                for stage in data:
                    if stage!='current':checks.append({'stage':stage,'view':name,**metrics.metric(frames['current'],frames[stage])})
            result={'group':group,'current_placed_triangles':sum(c['current_triangles']*c['uses'] for c in rows),'angular_placed_triangles':sum(c['native_angular_trial']['triangles']*c['uses'] for c in rows),'current_definition_triangles':sum(c['current_triangles'] for c in rows),'angular_definition_triangles':sum(c['native_angular_trial']['triangles'] for c in rows),'current_frozen_placed_triangles':sum(sum(m['current_triangles'] for m in c['current_materials'] if m['frozen_by_generic_colour_policy'])*c['uses'] for c in rows),'small_bore_discovery_count':sum(c['small_bore_candidates'] for c in rows),'current_small_units_17mm_placed_triangles':sum(c['current_small_units']['17']['triangles']*c['uses'] for c in rows),'source_units':sum(c['source_units'] for c in rows),'native_import_shells':sum(c['native_import_shells'] for c in rows),'qualities':qualities,'views':checks};results.append(result);print(group,result['current_placed_triangles'],'angular',result['angular_placed_triangles'],flush=True)
    report={'groups':results,'fan_trial':{k:v for k,v in fan.items() if k!='lod'},'approved_field_placed_triangles':3075154,'selected_groups_placed_triangles':sum(g['current_placed_triangles'] for g in results),'audit_sha256':digest(out/'audit.json'),'fan_trial_sha256':digest(out/'fan-trial.json'),'producer_sha256':digest(Path(__file__)),'scope':'Read-only opportunity study. Native family costs and current LOD costs are separate. Trial exports preserve CAD and face styles, but not bit-exact light geometry/shading; no candidate installed or promoted. 14 matched 1200² flat source-pose views, not runtime PBR/motion validation.'};(out/'review.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
