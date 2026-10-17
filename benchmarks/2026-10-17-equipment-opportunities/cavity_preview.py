#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render the qualified Energy Unit cavity omission, including the coarse trial."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import digest,build_plan
from mesh_quality import deviation

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();cid='energy-unit/unit';source=ROOT/'out/rmuc2027-equipment-pipeline'/cid;report=json.loads((out/'cavities.json').read_bytes());record=next(c for c in report['components'] if c['id']==cid);check=record['checks'][0]
    if not check['accepted'] or check['removed_native_shell_indices']!=[2] or digest(source/'source.step')!=record['source_step_sha256']:raise ValueError('no qualified cavity')
    pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');loader=module('loader',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py');attributes=module('attributes',ROOT/'benchmarks/2026-10-17-equipment-structure/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py')
    counts={};paths={'current':source/'lod.glb','angular':out/cid/'native-angular-trial.glb'}
    for stage,path in [('cavity-only',source/'lod.npz'),('angular-cavity',out/cid/'native-angular-trial.npz')]:
        mesh=np.load(path)
        if set(mesh['unit_ids'])!={1,2}:raise ValueError('source shell identity changed')
        mask=mesh['unit_ids']==1;pipeline.save_mesh(out,stage,mesh['positions_mm'],mesh['triangles'][mask],mesh['material_ids'][mask],[s or None for s in mesh['palette'].tolist()],mesh['unit_ids'][mask]);paths[stage]=out/(stage+'.glb');counts[stage]=int(mask.sum())
    before=attributes.payload(paths['current']);after=attributes.payload(paths['cavity-only'])
    if set(after)!={1} or set(before[1])!=set(after[1]) or any(not np.array_equal(before[1][k][0],after[1][k][0]) for k in before[1]):raise ValueError('cavity-only trial altered exterior attributes')
    pose=next(n['world_matrix_mm'] for n in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes'] if n['component_id']==cid);rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])@np.array(pose)[:3,:3];data={stage:loader.load(p) for stage,p in paths.items()};data={stage:(v[0]@rotation.T,v[1],v[2]) for stage,v in data.items()};views=[]
    for el,azs in [(15,range(0,360,45)),(45,range(0,360,90))]:
        for az in azs:
            e=math.radians(el);z=math.radians(az);views.append((f'e{el}-a{az}',(math.cos(z)*math.cos(e),math.sin(e),math.sin(z)*math.cos(e))))
    views += [('top',(0,1,.000001)),('bottom',(0,-1,.000001))];checks=[];image_folder=out/'review/Energy Units'
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for name,view in views:
            images={stage:raster.raster(v[0],v[1],data['current'][0],view,helper,tmp,image_folder/(stage+'-'+name+'.png')) for stage,v in data.items()}
            for stage in ['cavity-only','angular-cavity']:checks.append({'stage':stage,'view':name,**metrics.metric(images['current'],images[stage]),'matches_angular_image_exactly':bool(np.array_equal(images[stage],images['angular']))})
    native=np.load(source/'native.npz');coarse=np.load(out/'angular-cavity.npz');quality=deviation(native['positions_mm'],native['triangles'][native['unit_ids']==1],coarse['positions_mm'],coarse['triangles'],count=8192)
    result={'id':cid,'counts':counts,'uses':12,'exterior_attributes_exact_for_cavity_only':True,'angular_outer_native_sampled_deviation_mm':quality,'views':checks,'outputs_sha256':{stage:digest(paths[stage]) for stage in counts},'cavity_proof_sha256':digest(out/'cavities.json'),'producer_sha256':digest(Path(__file__))};(out/'cavity-preview.json').write_text(json.dumps(result,indent=2)+'\n');print(counts,'max cavity-only foreground',max(c['foreground_difference_relative_fraction'] for c in checks if c['stage']=='cavity-only'),flush=True)

if __name__=='__main__':main()
