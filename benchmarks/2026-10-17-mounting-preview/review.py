#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render independent work-part and mounting-detail comparisons for human review."""
import argparse,collections,importlib.util,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from export_field_package import GlbWriter
from plan_cad_lods import build_plan,digest
from gltf_scene import read_glb,accessor


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def attribute_payload(path):
    doc,blob=read_glb(path);result={}
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        for prim in doc['meshes'][node['mesh']]['primitives']:
            t=accessor(doc,blob,prim['indices']).reshape(-1,3);p=accessor(doc,blob,prim['attributes']['POSITION'])[t];n=accessor(doc,blob,prim['attributes']['NORMAL'])[t];material=doc['materials'][prim['material']];colour=material['extras']['step_colour_srgb'];key=None if colour is None else tuple(colour);result[key]=(np.c_[p.reshape(-1,9),n.reshape(-1,9)],material)
    return result


def check_attributes(folder,row):
    if 'proof' not in row['stages']['before']:return {'scope':'Whole assembly; source work-part attributes checked independently.'}
    before=attribute_payload(folder/'before.glb');reference=np.load(folder/'before.npz');palette=[None if not v else tuple(map(float,v.split(','))) for v in reference['palette'].tolist()];checks={}
    for stage in ['holes','fasteners','combined']:
        keep=np.array(row['stages'][stage]['proof']['unchanged_input_triangle_indices']);after=attribute_payload(folder/(stage+'.glb'));count=0
        for index,colour in enumerate(palette):
            ids=np.flatnonzero(reference['material_ids']==index);selected=np.isin(ids,keep);n=int(selected.sum())
            if not n:continue
            if colour not in before or colour not in after or before[colour][1]!=after[colour][1] or not np.array_equal(before[colour][0][selected],after[colour][0][:n]):raise ValueError('untouched exported positions/normals/materials changed')
            count+=n
        checks[stage]={'unchanged_exported_triangles_exact_positions_normals_materials':count}
    return checks


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--id');a=ap.parse_args();out=a.out.resolve();audit_path=ROOT/'out/rmuc2027-mounting-details/audit-final.json';audit=json.loads(audit_path.read_bytes());poses={}
    for node in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes']:
        if node['component_id']:poses.setdefault(node['component_id'],np.array(node['world_matrix_mm']))
    loader=module('loader',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');results=[];stages=['before','holes','fasteners','combined'];yup=np.array([[1,0,0],[0,0,1],[0,-1,0]])
    with tempfile.TemporaryDirectory() as temporary:
        tmp=Path(temporary);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        work_items=json.loads((out/'summary.json').read_bytes())['components'] if (out/'summary.json').exists() else audit['components']
        for entry in work_items:
            cid=entry['id']
            if a.id and cid!=a.id:continue
            folder=out/cid;record_path=folder/'summary.json'
            if not record_path.exists():raise ValueError('missing generated candidate '+cid)
            row=json.loads(record_path.read_bytes());review_path=folder/'review.json'
            if review_path.exists():
                cached=json.loads(review_path.read_bytes())
                if cached['summary_sha256']!=digest(record_path) or cached['producer_sha256']!=digest(Path(__file__)):raise ValueError('stale comparison')
                results.append(cached);continue
            attribute_checks=check_attributes(folder,row)
            rotation=np.array(row['display_rotation']) if 'display_rotation' in row else yup@poses[cid][:3,:3];display=np.eye(4);display[:3,:3]=rotation;data={}
            for stage in stages:
                if digest(folder/(stage+'.glb'))!=row['stages'][stage]['outputs_sha256'][stage+'.glb']:raise ValueError('candidate changed')
                g,c,u=loader.load(folder/(stage+'.glb'));data[stage]=(g@rotation.T,c)
                mesh=np.load(folder/(stage+'.npz'));palette=[v or None for v in mesh['palette'].tolist()];writer=GlbWriter(cid,{'version':'2.0','copyright':'DJI / RoboMaster source geometry/appearance; visual mounting-removal diagnostic'})
                writer.add_node('visual-surface-preview',mesh['positions_mm']/1000,mesh['triangles'],[palette[k] for k in mesh['material_ids']],matrix=display,extras={'component_id':cid,'visual_only':True,'collision_eligible':False,'variant':stage,'source_step_sha256':row['source_step_sha256']});writer.write(folder/(stage+'-inspection.glb'))
            reference=data['before'][0];views=[('oblique',(1,.5,1),reference),('reverse',(-1,.5,-1),reference),('front',(0,.000001,1),reference),('top',(0,1,.000001),reference)]
            holes=[r for r in audit['findings']['openings'] if cid in r['components'] and r['kind']=='circular-opening']
            if holes:
                cells=collections.defaultdict(list)
                for h in holes:cells[tuple(np.floor(np.array(h['center_mm'])/100).astype(int))].append(h)
                cluster=max(cells.values(),key=len);center=np.mean([h['center_mm'] for h in cluster],axis=0)/1000@rotation.T;cube=np.array([[x,y,z] for x in [-.075,.075] for y in [-.075,.075] for z in [-.075,.075]])+center;frame=cube[[0,1,2,3,4,5,6,7,0]].reshape(-1,3,3);normal=rotation@np.array(cluster[0]['axis_direction']);views.extend([('detail',normal,frame),('detail-reverse',-normal,frame)])
            images=folder/'review';images.mkdir(exist_ok=True);tests=[]
            for name,view,framing in views:
                frames={stage:raster.raster(g,c,framing,view,helper,tmp,images/(stage+'-'+name+'.png')) for stage,(g,c) in data.items()}
                for stage in stages[1:]:tests.append({'variant':stage,'view':name,**metrics.metric(frames['before'],frames[stage])})
                # Compact lossless sheets keep the interactive global gallery small.
                sheet=Image.new('RGB',(4*600,600))
                for i,stage in enumerate(stages):sheet.paste(Image.fromarray(frames[stage]).resize((600,600),Image.Resampling.LANCZOS),(i*600,0))
                sheet.save(images/(name+'.webp'),lossless=True,method=4)
            result={'id':cid,'summary_sha256':digest(record_path),'producer_sha256':digest(Path(__file__)),'exported_attribute_checks':attribute_checks,'views':tests,'view_names':[v[0] for v in views],'maximum_whole_foreground_difference':{stage:max(r['foreground_difference_relative_fraction'] for r in tests if r['variant']==stage and not r['view'].startswith('detail')) for stage in stages[1:]},'scope':'Matched source-pose two-sided flat source-colour renders for four variants; detail crops are framing changes, no geometry sliced or hidden for the camera. Definition comparison, not motion/PBR/collision validation.'};review_path.write_text(json.dumps(result,indent=2)+'\n');results.append(result);print('reviewed',cid,result['maximum_whole_foreground_difference'],flush=True)
    (out/'review.json').write_text(json.dumps({'components':results,'producer_sha256':digest(Path(__file__))},indent=2)+'\n')
if __name__=='__main__':main()
