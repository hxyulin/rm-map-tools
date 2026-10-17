#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verify actual attributes and compare isolated shells and complete equipment."""
import argparse,collections,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,accessor
from export_field_package import GlbWriter
from plan_cad_lods import digest,build_plan
from mesh_quality import deviation

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def payload(path):
    doc,blob=read_glb(path);result={}
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        unit=node['extras']['native_shell_index'];parts={}
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            t=accessor(doc,blob,primitive['indices']).reshape(-1,3);p=accessor(doc,blob,primitive['attributes']['POSITION'])[t];n=accessor(doc,blob,primitive['attributes']['NORMAL'])[t];material=doc['materials'][primitive['material']];colour=material['extras']['step_colour_srgb'];key=json.dumps(material,sort_keys=True);data=np.c_[p.reshape(-1,9),n.reshape(-1,9)];packed=np.ascontiguousarray(data).view(np.dtype((np.void,data.dtype.itemsize*18))).ravel();parts[key]=(np.sort(packed),colour,len(t))
        result[unit]=parts
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());source=ROOT/'out/rmuc2027-equipment-pipeline';prior=json.loads((source/'passes.json').read_bytes());loader=module('pipeline_review',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');poses={}
    for n in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes']:
        if n['component_id']:poses.setdefault(n['component_id'],np.array(n['world_matrix_mm']))
    y_up=np.array([[1,0,0],[0,0,1],[0,-1,0]]);results=[];views=[]
    for el,azimuths in [(15,range(0,360,30)),(45,range(0,360,90))]:
        for az in azimuths:
            e=math.radians(el);z=math.radians(az);views.append((f'e{el}-a{az}',(math.cos(z)*math.cos(e),math.sin(e),math.sin(z)*math.cos(e))))
    views += [('top',(0,1,.000001)),('bottom',(0,-1,.000001))]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for change in summary['components']:
            cid=change['id'];group=cid.split('/')[0];folder=out/cid;reference=source/cid/'lod.glb';candidate=folder/'candidate.glb'
            if digest(reference)!=change['approved_glb_sha256'] or digest(candidate)!=change['outputs_sha256']['candidate.glb']:raise ValueError('candidate/reference changed')
            before=payload(reference);after=payload(candidate);exact=0;protected_triangles=0
            if set(before)!=set(after):raise ValueError('shell ownership changed')
            for unit,parts in before.items():
                for key,(data,colour,count) in parts.items():
                    protected=colour is None or np.ptp(colour)>.1
                    if unit!=1 or protected:
                        if key not in after[unit] or not np.array_equal(data,after[unit][key][0]):raise ValueError('protected attribute payload changed')
                        if unit==1:protected_triangles+=count
                if unit!=1:exact+=1
            baseline=loader.load(reference);modified=loader.load(candidate);native=loader.load(source/cid/'native.glb');old=native[0][native[2]==1]*1000;new=modified[0][modified[2]==1]*1000;quality=deviation(old.reshape(-1,3),np.arange(len(old)*3).reshape(-1,3),new.reshape(-1,3),np.arange(len(new)*3).reshape(-1,3),count=32768)
            if quality['max']>3.001:raise ValueError('exported native guard failed')
            rotation=y_up@poses[cid][:3,:3];display=np.eye(4);display[:3,:3]=rotation;compositions={};counts={}
            for stage in ['before','after']:
                rows=[r for r in prior['components'] if r['id'].split('/')[0]==group];pieces=[];writer=GlbWriter(group,{'version':'2.0','copyright':'DJI / RoboMaster source geometry and appearance; inspected structural LOD'})
                for r in rows:
                    path=folder/'candidate' if stage=='after' and r['id']==cid else source/r['id']/'lod';data=loader.load(path.with_suffix('.glb'));pieces.append(data);mesh=np.load(path.with_suffix('.npz'));palette=[v or None for v in mesh['palette'].tolist()]
                    for unit in np.unique(mesh['unit_ids']):
                        ids=mesh['unit_ids']==unit;used,inv=np.unique(mesh['triangles'][ids],return_inverse=True);writer.add_node(r['id']+'/shell-'+str(unit),mesh['positions_mm'][used]/1000,inv.reshape(-1,3),[palette[k] for k in mesh['material_ids'][ids]],matrix=display,extras={'component_id':r['id'],'native_shell_index':int(unit),'inspection_only':True})
                data=tuple(np.concatenate([v[k] for v in pieces]) for k in range(3));compositions[stage]=(data[0]@rotation.T,data[1],data[2]);counts[stage]=len(data[0]);writer.write(out/(group+'-'+stage+'.glb'))
            tests=[]
            selections={'whole':compositions,'component':{'before':baseline,'after':modified},'shell':{'before':tuple(v[baseline[2]==1] for v in baseline),'after':tuple(v[modified[2]==1] for v in modified)}}
            for scope,versions in selections.items():
                if scope!='whole':versions={stage:(data[0]@rotation.T,data[1],data[2]) for stage,data in versions.items()}
                images=out/'review'/group/scope;images.mkdir(parents=True,exist_ok=True)
                for name,view in views:
                    frames={stage:raster.raster(data[0],data[1],versions['before'][0],view,helper,tmp,images/(stage+'-'+name+'.png')) for stage,data in versions.items()};tests.append({'scope':scope,'view':name,**metrics.metric(frames['before'],frames['after'])})
            result={'id':cid,'unchanged_shells_exact_positions_normals_materials':exact,'protected_main_shell_triangles_exact_positions_normals_materials':protected_triangles,'exported_native_sampled_deviation_mm':quality,'component_before':change['approved_triangles'],'component_after':change['candidate_triangles'],'whole_before':counts['before'],'whole_after':counts['after'],'placed_saving':2*(counts['before']-counts['after']),'views':tests,'whole_glb_sha256':{stage:digest(out/(group+'-'+stage+'.glb')) for stage in compositions}};results.append(result);print(cid,counts,quality,flush=True)
    total_saving=sum(r['placed_saving'] for r in results);report={'components':results,'previous_field_placed_triangles':3805082,'placed_triangle_saving':total_saving,'candidate_field_placed_triangles':3805082-total_saving,'input_summary_sha256':digest(out/'summary.json'),'producer_sha256':digest(Path(__file__)),'scope':'18 matched views for whole product, changed component and changed shell. Exact unselected/protected GLB positions, normals and full materials. Sampled native distance, flat source-pose rendering; not continuous distance, runtime PBR, moving poses or collision validation.'};(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
