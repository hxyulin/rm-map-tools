#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose source-member skin candidates, preserving approved light primitives."""
import argparse,copy,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,write_glb
from simplify_package import compact,scene_triangles
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('previous',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/compose.py');previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
spec=importlib.util.spec_from_file_location('audit',Path(__file__).with_name('audit.py'));audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

def light(doc,p):
    c=np.array(doc['materials'][p['material']]['extras']['step_colour_srgb']);return c[0]>.9 and c[1]<.1 or c[1]>.9 and c[0]<.1

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--backing-plates',action='store_true');a=ap.parse_args();a.out.mkdir(exist_ok=True,parents=True);source=ROOT/'out/rmuc2027-base-aggressive-final/base-visual.glb';baseline=json.loads((source.parent/'composition.json').read_bytes())
    if digest(source)!=baseline['base_glb_sha256']:raise ValueError('approved reference changed')
    skins=ROOT/'out/rmuc2027-base-planar-skins';skin_report=json.loads((skins/'summary.json').read_bytes());bar=ROOT/'out/rmuc2027-base-crossbar-skin';bar_report=json.loads((bar/'summary.json').read_bytes());replacements={u['source_unit_id']:skins/str(u['source_unit_id']) for u in skin_report['units'] if u['after_triangles']<u['before_triangles'] and u['source_unit_id']!=4268930};replacements[4268930]=bar
    if a.backing_plates:
        plates=ROOT/'out/rmuc2027-base-backing-plates';plate_report=json.loads((plates/'summary.json').read_bytes())
        for u in plate_report['units']:replacements[u['source_unit_id']]=plates/str(u['source_unit_id'])
    doc,blob=read_glb(source);original=copy.deepcopy(doc);original_blob=blob;data=bytearray(blob)
    for source_id,folder in replacements.items():
        other,binary=read_glb(folder/'visual.glb');nodes=[n for n in doc['nodes'] if n.get('extras',{}).get('source_unit_id')==source_id]
        if len(nodes)!=1 or len(other['meshes'])!=1:raise ValueError('source member not unique')
        old_lights=[copy.deepcopy(p) for p in doc['meshes'][nodes[0]['mesh']]['primitives'] if light(doc,p)];data.extend(b'\0'*(-len(data)%4));offset=len(data);data.extend(binary);vo=len(doc['bufferViews']);ao=len(doc['accessors'])
        for v in other['bufferViews']:
            v=copy.deepcopy(v);v['buffer']=0;v['byteOffset']=v.get('byteOffset',0)+offset;doc['bufferViews'].append(v)
        for v in other['accessors']:
            v=copy.deepcopy(v);v['bufferView']+=vo;doc['accessors'].append(v)
        mesh=copy.deepcopy(other['meshes'][0]);mesh['primitives']=[p for p in mesh['primitives'] if not light(other,p)]
        for p in mesh['primitives']:
            p['attributes']={k:v+ao for k,v in p['attributes'].items()};p['indices']+=ao;m=other['materials'][p['material']];matches=[i for i,x in enumerate(doc['materials']) if x.get('extras',{}).get('step_colour_srgb')==m['extras']['step_colour_srgb']]
            if len(matches)!=1:raise ValueError('material match not unique')
            target=doc['materials'][matches[0]]
            if {k:v for k,v in m.items() if k!='name'}!={k:v for k,v in target.items() if k!='name'}:raise ValueError('shader changed')
            p['material']=matches[0]
        mesh['primitives'].extend(old_lights);nodes[0]['mesh']=len(doc['meshes']);doc['meshes'].append(mesh)
    doc['asset'].setdefault('extras',{})['inspection_composition']={'scope':'Planar skins and source-outline backing trial; not installed; collision unchanged','backing_plates':a.backing_plates,'replaced_source_units':sorted(replacements)};data=compact(doc,data);write_glb(a.out/'base-visual.glb',doc,data);doc,data=read_glb(a.out/'base-visual.glb');unchanged=0;lights=0;counts=[]
    for old,new in zip(original['nodes'],doc['nodes']):
        if {k:v for k,v in old.items() if k!='mesh'}!={k:v for k,v in new.items() if k!='mesh'}:raise ValueError('source member metadata changed')
        if 'mesh' not in old:continue
        old_led=previous.payload(original,original_blob,old,True);new_led=previous.payload(doc,data,new,True)
        if not previous.equal(old_led,new_led):raise ValueError('approved light attributes changed')
        lights+=sum(len(p[0])//3 for p in old_led)
        if old.get('extras',{}).get('source_unit_id') not in replacements:
            if not previous.equal(previous.payload(original,original_blob,old),previous.payload(doc,data,new)):raise ValueError('unselected member changed')
            unchanged+=1
        else:counts.append({'source_unit_id':old['extras']['source_unit_id'],'before_triangles':sum(len(p[0])//3 for p in previous.payload(original,original_blob,old)),'after_triangles':sum(len(p[0])//3 for p in previous.payload(doc,data,new)),'replacement_sha256':digest(replacements[old['extras']['source_unit_id']]/'visual.glb')})
    actual=scene_triangles(doc)
    if actual!=82414-sum(u['before_triangles']-u['after_triangles'] for u in counts):raise ValueError('count mismatch')
    result={'source_sha256':digest(source),'base_glb_sha256':digest(a.out/'base-visual.glb'),'before_triangles':82414,'after_triangles':actual,'saved_triangles':82414-actual,'saved_fraction':1-actual/82414,'base_glb_bytes':(a.out/'base-visual.glb').stat().st_size,'two_placed_bases_triangles':actual*2,'exact_light_triangles':lights,'unselected_members_exact_rendered_attributes':unchanged,'collision_triangles_unchanged':16857,'backing_plates':a.backing_plates,'replacements':counts,'producer_sha256':digest(Path(__file__))};(a.out/'composition.json').write_text(json.dumps(result,indent=2)+'\n');npz,_=audit.load(a.out/'base-visual.glb');np.savez(a.out/'geometry.npz',**npz);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
