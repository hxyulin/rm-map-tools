#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose full inspection Base while retaining untouched GLB attributes exactly."""
import argparse,copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,write_glb,accessor
from simplify_package import compact,scene_triangles
from plan_cad_lods import digest


def payload(doc,binary,node):
    return [(accessor(doc,binary,p['attributes']['POSITION']),accessor(doc,binary,p['attributes']['NORMAL']),accessor(doc,binary,p['indices']),doc['materials'][p['material']]) for p in doc['meshes'][node['mesh']]['primitives']]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;report=json.loads((out/'summary.json').read_bytes());source=ROOT/'out/rmuc2027-base-light-final/ico2/visual.glb';doc,blob=read_glb(source);original=copy.deepcopy(doc);original_blob=blob;data=bytearray(blob);changed={4268930,4527988};bar=ROOT/'out/rmuc2027-base-top-mounting-row-final';bar_report=json.loads((bar/'summary.json').read_bytes());lights=json.loads((ROOT/'out/rmuc2027-base-light-final/summary.json').read_bytes())
    if digest(source)!=lights['stages']['ico2']['visual_sha256']:raise ValueError('approved light Base changed')
    replacements=[(4268930,bar/'visual.glb',bar_report['visual_sha256']),(4527988,out/'visual.glb',report['visual_sha256'])]
    for source_id,path,expected in replacements:
        if digest(path)!=expected:raise ValueError('replacement checksum mismatch')
        other,binary=read_glb(path);nodes=[n for n in doc['nodes'] if n.get('extras',{}).get('source_unit_id')==source_id]
        if len(nodes)!=1 or len(other['meshes'])!=1:raise ValueError('expected one source member/replacement mesh')
        data.extend(b'\0'*(-len(data)%4));offset=len(data);data.extend(binary);view_offset=len(doc['bufferViews']);accessor_offset=len(doc['accessors'])
        for view in other['bufferViews']:
            view=copy.deepcopy(view)
            if view.get('buffer',0)!=0:raise ValueError('external buffer unsupported')
            view['buffer']=0;view['byteOffset']=view.get('byteOffset',0)+offset;doc['bufferViews'].append(view)
        for item in other['accessors']:
            item=copy.deepcopy(item);item['bufferView']+=view_offset;doc['accessors'].append(item)
        mesh=copy.deepcopy(other['meshes'][0])
        for prim in mesh['primitives']:
            for attr in prim['attributes']:prim['attributes'][attr]+=accessor_offset
            prim['indices']+=accessor_offset;material=other['materials'][prim['material']];rgb=material['extras']['step_colour_srgb'];matches=[i for i,m in enumerate(doc['materials']) if m.get('extras',{}).get('step_colour_srgb')==rgb]
            if len(matches)!=1:raise ValueError('replacement material absent or ambiguous')
            base_material=doc['materials'][matches[0]]
            if {k:v for k,v in material.items() if k!='name'}!={k:v for k,v in base_material.items() if k!='name'}:raise ValueError('replacement shader differs from source')
            prim['material']=matches[0]
        nodes[0]['mesh']=len(doc['meshes']);doc['meshes'].append(mesh)
    doc.setdefault('asset',{}).setdefault('extras',{})['inspection_composition']={'replaced_source_units':sorted(changed),'scope':'Approved light Base with approved top crossbar and candidate local housing LOD; no runtime or collider installation.'};data=compact(doc,data);write_glb(out/'base-visual.glb',doc,data);doc,data=read_glb(out/'base-visual.glb');checked=0
    for old,new in zip(original['nodes'],doc['nodes']):
        if old.get('extras',{}).get('source_unit_id') in changed:continue
        if {k:v for k,v in old.items() if k!='mesh'}!={k:v for k,v in new.items() if k!='mesh'}:raise ValueError('unselected node metadata changed')
        if 'mesh' not in old:continue
        old_p=payload(original,original_blob,old);new_p=payload(doc,data,new)
        if len(old_p)!=len(new_p):raise ValueError('primitive count changed')
        for x,y in zip(old_p,new_p):
            if not all(np.array_equal(x[i],y[i]) for i in range(3)) or x[3]!=y[3]:raise ValueError('untouched GLB position/normal/index/material changed')
        checked+=1
    if scene_triangles(doc)!=report['base_triangles']:raise ValueError('composed triangle total differs')
    result={'source_glb_sha256':digest(source),'base_glb_sha256':digest(out/'base-visual.glb'),'base_glb_bytes':(out/'base-visual.glb').stat().st_size,'visual_triangles':scene_triangles(doc),'byte_exact_unselected_member_attributes':checked,'replaced_source_unit_ids':sorted(changed),'smooth_optic_attributes_preserved':True,'producer_sha256':digest(Path(__file__))};(out/'composition.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
