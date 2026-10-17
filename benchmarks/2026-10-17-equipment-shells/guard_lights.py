#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Restore source face neighborhoods that change assembled primary-light masks.

This only requests more source geometry be retained. It never deletes a part
because another independently moving component happens to occlude it.
"""
import argparse
import collections
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from common import ROOT,module,read_mesh
import numpy as np
from gltf_scene import read_glb,scene_nodes
from cad_dense_lod import surface_samples
from plan_cad_lods import digest


def primary(image):
    rgb=image.astype(float);return ((rgb[:,:,0]>40)&(rgb[:,:,0]>2*rgb[:,:,1]+10)&(rgb[:,:,0]>2*rgb[:,:,2]+10))|((rgb[:,:,1]>40)&(rgb[:,:,1]>2*rgb[:,:,0]+10)&(rgb[:,:,1]>2*rgb[:,:,2]+10))


def full_metadata(path):
    d,b=read_glb(path);local=[];members=[];components=[];poses={};cursor=collections.Counter()
    for i,world,_ in scene_nodes(d):
        n=d['nodes'][i];e=n.get('extras',{})
        if 'source_hierarchy_node_id'in e:poses[e['source_hierarchy_node_id']]=world
        if 'mesh'not in n:continue
        occurrence=e['composition_occurrence'];key=occurrence['node_id'];u=e.get('source_native_shell_index',e.get('native_shell_index'))
        for prim in d['meshes'][n['mesh']]['primitives']:
            count=d['accessors'][prim['indices']]['count']//3;local.extend(range(cursor[key],cursor[key]+count));cursor[key]+=count;members.extend([u]*count);components.extend([occurrence['component_id']]*count)
    return np.array(local),np.array(members),np.array(components),poses


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();baseline=ROOT/'out/rmuc2027-dart-outpost/candidate-field.glb';candidate=out/'candidate-field.glb';old=json.loads((ROOT/'out/rmuc2027-dart-outpost/summary.json').read_bytes());by={r['id']:r for r in old['components']};scene=module('scene',ROOT/'benchmarks/2026-10-17-composed-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py').raster;data={};owners={};metadata={}
    for stage,path in [('reference',baseline),('candidate',candidate)]:data[stage],owners[stage]=scene.load_scene(path);metadata[stage]=full_metadata(path)
    first=next(v for v in owners['reference'].values()if v['component_id'].startswith('outpost/'));g=data['reference'][0][data['reference'][4]==first['index']];anchor=(g.min((0,1))+g.max((0,1)))/2;parts={s:scene.select(d,owners[s],'outpost',anchor)for s,d in data.items()};global_ids={s:np.flatnonzero(np.isin(data[s][4],p[4]))for s,p in parts.items()};old_guards=out/'optical-guards.json';protected={};records=[];inputs={};cache={}
    if old_guards.exists():
        old_report=json.loads(old_guards.read_bytes())
        if old_report['reference_full_glb_sha256']!=digest(baseline):raise ValueError('optical guard baseline changed')
        for r in old_report['components']:protected[r['id']]=set(r['protected_input_triangle_indices'])
    def source(cid):
        if cid not in cache:
            path=ROOT/by[cid]['visual_glb'];cache[cid]=read_mesh(path);inputs[cid]=digest(path)
        return cache[cid]
    sys_path=__import__('sys').path;sys_path.insert(0,str(ROOT/'benchmarks/2026-10-17-collision-solids'));shared=module('contact_geometry',ROOT/'benchmarks/2026-10-17-collision-solids/validate.py');import vtk
    locators={}
    def nearest_source(cid,unit,queries):
        key=(cid,unit)
        if key not in locators:
            d=source(cid);mask=d['unit_ids']==unit;colors=np.array([[float(v)for v in c.split(',')]if c else[.6275]*3 for c in d['palette']]);gray=np.ptp(colors[d['material_ids']],axis=1)<.1
            if (mask&gray).any():mask&=gray
            ids=np.flatnonzero(mask);p,t=d['positions_mm'],d['triangles'];locator=vtk.vtkStaticCellLocator();locator.SetDataSet(shared.polydata(p,t[ids]));locator.BuildLocator();locators[key]=(locator,ids)
        locator,ids=locators[key];found=set()
        for point in queries:
            closest=[0.,0.,0.];cell=vtk.reference(0);sub=vtk.reference(0);distance=vtk.reference(0.);locator.FindClosestPoint(point,closest,cell,sub,distance);found.add(int(ids[int(cell)]))
        return found
    views=[('oblique',(1,.7,1.5)),('reverse',(-1,.7,-1.5)),('top',(0,1,.000001)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('bottom',(0,-1,.000001)),('side',(1,.000001,0))]
    with tempfile.TemporaryDirectory()as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for name,view in views:
            images={};pixel_ids={}
            for stage,d in parts.items():images[stage]=raster(d[0],d[1],parts['reference'][0],view,helper,tmp);pixel_ids[stage]=np.fromfile(tmp/'owners.bin',dtype='<i4').reshape(1200,1200)
            before,after=primary(images['reference']),primary(images['candidate']);extra=after&~before;missing=before&~after;record={'view':name,'reference_light_pixels':int(before.sum()),'candidate_light_pixels':int(after.sum()),'changed_pixels':int((before^after).sum()),'newly_exposed_pixels':int(extra.sum()),'newly_hidden_pixels':int(missing.sum())};records.append(record)
            for triangle in np.unique(pixel_ids['reference'][extra]):
                if triangle<0:continue
                gi=global_ids['reference'][triangle];cid=str(metadata['reference'][2][gi]);local=int(metadata['reference'][0][gi]);protected.setdefault(cid,set()).add(local);source(cid)
            for triangle in np.unique(pixel_ids['candidate'][missing]):
                if triangle<0:continue
                gi=global_ids['candidate'][triangle];cid=str(metadata['candidate'][2][gi]);unit=int(metadata['candidate'][1][gi]);d=source(cid);occurrence_index=parts['candidate'][4][triangle];key=next(k for k,v in owners['candidate'].items()if v['index']==occurrence_index);pose=metadata['candidate'][3][key];world_points=parts['candidate'][0][triangle];local_points=(world_points-pose[:3,3])@np.linalg.inv(pose[:3,:3]).T*1000;queries=surface_samples(local_points,np.array([[0,1,2]])).reshape(-1,3);protected.setdefault(cid,set()).update(nearest_source(cid,unit,queries))
            print(name,'light-mask changed pixels',record['changed_pixels'],flush=True)
    rows=[]
    for cid,ids in sorted(protected.items()):
        if not cid.startswith('outpost/'):raise ValueError('unexpected optical repair scope')
        source(cid);rows.append({'id':cid,'source_visual_sha256':inputs[cid],'protected_input_triangle_indices':sorted(ids)})
    passed=all(r['changed_pixels']<=max(12,.02*r['reference_light_pixels'])for r in records);result={'components':rows,'views':records,'passes_light_mask_guard':passed,'reference_full_glb_sha256':digest(baseline),'candidate_full_glb_sha256':digest(candidate),'producer_sha256':digest(__file__),'scope':'Seven source-pose whole-Outpost primary-color mask comparisons. More original source triangles are protected on mismatch. This retains geometry rather than authorizing cross-motion occlusion deletion; not all-motion/PBR proof.'};old_guards.write_text(json.dumps(result,indent=2)+'\n');print('protected triangles',sum(len(r['protected_input_triangle_indices'])for r in rows),'passed',passed)


if __name__=='__main__':main()
