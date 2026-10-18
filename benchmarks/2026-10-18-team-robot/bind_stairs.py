#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Bind DreamChaser's closed wheel linkage, keeping its upper Engineer arm static."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,write_glb,mesh_instances
from export_field_package import GlbWriter
from stair_linkage import BODY_SOURCE_M,C,TRAVEL_RAD,DEPLOYED_RAD,frames,group
from robot_materials import apply_materials,verify_materials
from robot_armor import identify_armor,strip_armor_surfaces,verify_armor_replacement


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args();model='dreamchaser-2026-stair-engineer'
    source=json.loads(Path(__file__).with_name('candidates.json').read_text())['sources']['stair_heavy']
    assert sha(a.sources/(model+'.step'))==source['cad_sha256']
    rows=json.loads((a.sources/(model+'-hierarchy.json')).read_text())
    by_path={r['path']:r for r in rows};owners={sid:r['path'] for r in rows for sid in r.get('native_solids',[])}
    d,b=read_glb(a.sources/(model+'-pilot/low.glb'))
    center=np.array(json.loads((a.sources/(model+'-frame.json')).read_text())['source_center_mm'])/1000
    source_frames=frames(DEPLOYED_RAD-TRAVEL_RAD)
    parts=[];max_error=0.
    for ni,pi,p,t,mi in mesh_instances(d,b):
        node=d['nodes'][ni];extra=node['extras'];sid=extra['native_solid_index']
        path=extra.get('source_leaf_path') or owners[sid];link=group(path)
        body=p+center-BODY_SOURCE_M
        frame=source_frames[link]
        local=(body-frame[:3,3])@frame[:3,:3]
        max_error=max(max_error,float(np.max(np.abs(local@frame[:3,:3].T+frame[:3,3]-body))))
        material=d['materials'][mi];color=None if material['extras']['step_colour_srgb'] is None else material['name'].removeprefix('colour_')
        parts.append((node['name']+f'-{pi}',local,t,color,link,{**extra,
            'source_occurrence_path':path,'source_definition_name':by_path[path]['name'],
            'source_occurrence_paths':[path],'motion_group':link,'articulation_bound':True}))
    a.out.mkdir(parents=True,exist_ok=True);stats={};files={};armor=None
    for name,angle in [('neutral',0.),('mid-climb',(DEPLOYED_RAD-TRAVEL_RAD)/2),('deployed',DEPLOYED_RAD-TRAVEL_RAD)]:
        writer=GlbWriter('dreamchaser-stair-heavy',{'version':'2.0','copyright':source['credit']+'; original CAD terms apply.'})
        groups={}
        for part,p,t,color,link,extra in parts:
            before=len(writer.nodes);writer.add_node(part,p,t,[color]*len(t),extras=extra)
            groups.setdefault(link,[]).extend(range(before+1,len(writer.nodes)+1))
        target=a.out/(name+'.glb');writer.write(target);out,binary=read_glb(target)
        bones={};posed=frames(angle)
        for link,matrix in posed.items():
            i=len(out['nodes']);bones[link]=i
            out['nodes'].append({'name':'link/'+link,'matrix':matrix.flatten(order='F').tolist(),'children':groups.get(link,[])})
        for link in posed:
            if link!='body':out['nodes'][bones['body']]['children'].append(bones[link])
        out['nodes'][0]['children']=[bones['body']]
        appearance=copy.deepcopy(out);payload,material_report=apply_materials(appearance,binary,rows)
        verify_materials(out,binary,appearance,payload)
        if armor is None:
            armor=identify_armor(appearance,payload,rows)
            assert len(armor['modules'])==4
            for m in armor['modules']:
                matrix=np.array(m['face_matrix_gltf']).reshape(4,4,order='F');basis=C@matrix[:3,:3]
                q=Rotation.from_matrix(basis).as_quat()
                m['body_face_pose_flu']={'translation_m':(C@matrix[:3,3]).tolist(),'rotation_wxyz':q[[3,0,1,2]].tolist()}
                m['id']=int(np.round(np.arctan2(basis[1,0],basis[0,0])/(np.pi/2)))%4
            armor['modules'].sort(key=lambda m:m['id']);armor['runtime_replacement']=True
        stripped=copy.deepcopy(appearance);strip_armor_surfaces(stripped,armor)
        armor['validation']=verify_armor_replacement(appearance,stripped,armor)
        stripped['asset'].setdefault('extras',{})['armor_bindings']=armor
        write_glb(target,stripped,payload);files[name]={'file':name+'.glb','sha256':sha(target)}
        points=np.concatenate([p for _,_,p,_,_ in mesh_instances(stripped,payload)])
        stats[name]={'input_rad':angle,'bounds_body_gltf_m':[points.min(0).tolist(),points.max(0).tolist()]}
    manifest={'schema':3,'profile':'dreamchaser-stair-heavy-v1','source':source,'files':files,'armor':armor,
        'body_origin_gltf_m':[0,0,0],'source_body_origin_m':BODY_SOURCE_M.tolist(),'poses':stats,
        'producer_sha256':sha(Path(__file__)),'linkage_sha256':sha(ROOT/'python/stair_linkage.py'),
        'input_visual_sha256':sha(a.sources/(model+'-pilot/low.glb')),
        'source_reconstruction_error_m':max_error,'source_visual_triangles':sum(len(p[2]) for p in parts),
        'policy':'Closed planar linkage fitted to source bearings and technical report Figures 2–3. Upper arm and auxiliary sensor linkage are unactuated. Prescribed actuator and effective wheel suspension, not full multibody/torque validation.'}
    (a.out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (a.out/'CAD-NOTICE.md').write_text(source['credit']+'\n'+source['source_article']+'\n'+source['terms']+'\n'+manifest['policy']+'\n')
    print(json.dumps({'modules':len(armor['modules']),'source_triangles':manifest['source_visual_triangles'],'source_reconstruction_error_m':max_error}))


if __name__=='__main__':main()
