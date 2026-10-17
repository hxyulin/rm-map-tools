#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose aggressive inspection members and check untouched/light GLB payloads."""
import argparse,copy,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,write_glb,accessor
from simplify_package import compact,scene_triangles
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('members',Path(__file__).with_name('base.py'));members=importlib.util.module_from_spec(spec);spec.loader.exec_module(members)

def payload(doc,binary,node,only_lights=False):
    result=[]
    for p in doc['meshes'][node['mesh']]['primitives']:
        material=doc['materials'][p['material']];colour=np.asarray(material['extras']['step_colour_srgb'])
        if only_lights and not members.lights(colour[None])[0]:continue
        index=accessor(doc,binary,p['indices']).reshape(-1)
        result.append((accessor(doc,binary,p['attributes']['POSITION'])[index],accessor(doc,binary,p['attributes']['NORMAL'])[index],{k:v for k,v in material.items() if k!='name'}))
    return result

def equal(a,b):return len(a)==len(b) and all(np.array_equal(x[0],y[0]) and np.array_equal(x[1],y[1]) and x[2]==y[2] for x,y in zip(a,b))

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'out/rmuc2027-base-housing-local-final/base-visual.glb';housing=ROOT/'out/rmuc2027-base-housing-aggressive-sparse';bodies=ROOT/'out/rmuc2027-base-bodies-aggressive';body_report=json.loads((bodies/'summary.json').read_bytes());housing_report=json.loads((housing/'summary.json').read_bytes());baseline=json.loads((ROOT/'out/rmuc2027-base-housing-local-final/composition.json').read_bytes())
    if digest(source)!=baseline['base_glb_sha256']:raise ValueError('approved composition changed')
    replacements=[(4527988,housing,housing_report['visual_sha256'])]+[(d['source_unit_id'],bodies/str(d['source_unit_id']),d['visual_sha256']) for d in body_report['decisions'] if d['accepted']]
    doc,blob=read_glb(source);original=copy.deepcopy(doc);original_blob=blob;data=bytearray(blob);changed={s for s,_,_ in replacements}
    for source_id,folder,expected in replacements:
        if digest(folder/'visual.glb')!=expected:raise ValueError('replacement changed')
        other,binary=read_glb(folder/'visual.glb');nodes=[n for n in doc['nodes'] if n.get('extras',{}).get('source_unit_id')==source_id]
        if len(nodes)!=1 or len(other['meshes'])!=1:raise ValueError('source member not unique')
        data.extend(b'\0'*(-len(data)%4));offset=len(data);data.extend(binary);vo=len(doc['bufferViews']);ao=len(doc['accessors'])
        for v in other['bufferViews']:
            v=copy.deepcopy(v);v['buffer']=0;v['byteOffset']=v.get('byteOffset',0)+offset;doc['bufferViews'].append(v)
        for v in other['accessors']:
            v=copy.deepcopy(v);v['bufferView']+=vo;doc['accessors'].append(v)
        mesh=copy.deepcopy(other['meshes'][0])
        for p in mesh['primitives']:
            p['attributes']={k:v+ao for k,v in p['attributes'].items()};p['indices']+=ao;m=other['materials'][p['material']];matches=[i for i,x in enumerate(doc['materials']) if x.get('extras',{}).get('step_colour_srgb')==m['extras']['step_colour_srgb']]
            if len(matches)!=1:raise ValueError('material match not unique')
            target=doc['materials'][matches[0]]
            if {k:v for k,v in m.items() if k!='name'}!={k:v for k,v in target.items() if k!='name'}:raise ValueError('shader changed')
            p['material']=matches[0]
        nodes[0]['mesh']=len(doc['meshes']);doc['meshes'].append(mesh)
    doc['asset'].setdefault('extras',{})['inspection_composition']={'replaced_source_units':sorted(changed),'scope':'3 mm sampled visual detail candidate; native CAD, collision and installed assets unchanged'};data=compact(doc,data);write_glb(out/'base-visual.glb',doc,data);doc,data=read_glb(out/'base-visual.glb');unchanged=0;lights=0
    for old,new in zip(original['nodes'],doc['nodes']):
        if {k:v for k,v in old.items() if k!='mesh'}!={k:v for k,v in new.items() if k!='mesh'}:raise ValueError('node metadata changed')
        if 'mesh' not in old:continue
        if not equal(payload(original,original_blob,old,True),payload(doc,data,new,True)):raise ValueError('light GLB position/normal/material changed: '+str(old.get('extras')))
        lights+=sum(len(p[0])//3 for p in payload(original,original_blob,old,True))
        if old.get('extras',{}).get('source_unit_id') not in changed:
            if not equal(payload(original,original_blob,old),payload(doc,data,new)):raise ValueError('untouched payload changed')
            unchanged+=1
    expected=109860-(15832-housing_report['housing_triangles'])-sum(d['before_triangles']-d['after_triangles'] for d in body_report['decisions'] if d['accepted'])
    if scene_triangles(doc)!=expected:raise ValueError('triangle count mismatch')
    result={'source_glb_sha256':digest(source),'base_glb_sha256':digest(out/'base-visual.glb'),'base_glb_bytes':(out/'base-visual.glb').stat().st_size,'before_triangles':109860,'visual_triangles':expected,'saved_triangles':109860-expected,'saved_fraction':1-expected/109860,'placed_two_bases_triangles':2*expected,'unchanged_members':unchanged,'exact_light_triangles_positions_normals_materials':lights,'replaced_source_unit_ids':sorted(changed),'collision_triangles_unchanged':16857,'producer_sha256':digest(Path(__file__))};(out/'composition.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
