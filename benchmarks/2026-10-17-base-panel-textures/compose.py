#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compose local panel/texture trials while preserving other source members."""
import argparse,copy,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,write_glb
from simplify_package import compact,scene_triangles
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('old',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/compose.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)


def replace(doc,data,source_id,path):
    other,blob=read_glb(path);nodes=[n for n in doc['nodes'] if n.get('extras',{}).get('source_unit_id')==source_id]
    if len(nodes)!=1 or len(other['meshes'])!=1:raise ValueError('source member not unique')
    data.extend(b'\0'*(-len(data)%4));offset=len(data);data.extend(blob);vo=len(doc['bufferViews']);ao=len(doc['accessors']);io=len(doc.get('images',[]));so=len(doc.get('samplers',[]));to=len(doc.get('textures',[]));mo=len(doc['materials'])
    for v in other['bufferViews']:
        v=copy.deepcopy(v);v['buffer']=0;v['byteOffset']=v.get('byteOffset',0)+offset;doc['bufferViews'].append(v)
    for v in other['accessors']:
        v=copy.deepcopy(v);v['bufferView']+=vo;doc['accessors'].append(v)
    for v in other.get('images',[]):
        v=copy.deepcopy(v);v['bufferView']+=vo;doc.setdefault('images',[]).append(v)
    doc.setdefault('samplers',[]).extend(copy.deepcopy(other.get('samplers',[])))
    for v in other.get('textures',[]):
        v=copy.deepcopy(v);v['source']+=io
        if 'sampler' in v:v['sampler']+=so
        doc.setdefault('textures',[]).append(v)
    for v in other['materials']:
        v=copy.deepcopy(v)
        for key in ['baseColorTexture','metallicRoughnessTexture']:
            if key in v.get('pbrMetallicRoughness',{}):v['pbrMetallicRoughness'][key]['index']+=to
        for key in ['normalTexture','occlusionTexture','emissiveTexture']:
            if key in v:v[key]['index']+=to
        doc['materials'].append(v)
    mesh=copy.deepcopy(other['meshes'][0])
    for p in mesh['primitives']:
        p['attributes']={k:v+ao for k,v in p['attributes'].items()};p['indices']+=ao;p['material']+=mo
    nodes[0]['mesh']=len(doc['meshes']);doc['meshes'].append(mesh)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--panel',type=int,choices=[4202749,4196198]);ap.add_argument('--texture',action='store_true');a=ap.parse_args();a.out.mkdir(exist_ok=True,parents=True);source=ROOT/'out/rmuc2027-base-shells-final/base-visual.glb';expected=json.loads((source.parent/'composition.json').read_bytes())['base_glb_sha256']
    if digest(source)!=expected:raise ValueError('approved Base changed')
    doc,blob=read_glb(source);before=copy.deepcopy(doc);data=bytearray(blob);changed=[]
    if a.panel:
        folder=ROOT/'out/rmuc2027-base-panel-trials'/str(a.panel);qualification=json.loads((folder/'qualification.json').read_bytes());optimization=json.loads((folder/'optimization.json').read_bytes())
        if not qualification['accepted'] or digest(folder/'optimized.npz')!=qualification['candidate_sha256'] or digest(folder/'optimized.glb')!=optimization['visual_sha256']:raise ValueError('panel is unqualified or changed')
        replace(doc,data,4268930,folder/'optimized.glb');changed.append(4268930)
    if a.texture:
        folder=ROOT/'out/rmuc2027-base-logo-texture';report=json.loads((folder/'summary.json').read_bytes())
        if not report['accepted'] or digest(folder/'visual.glb')!=report['visual_sha256']:raise ValueError('texture member is unqualified or changed')
        replace(doc,data,4527988,folder/'visual.glb');changed.append(4527988)
    doc['asset'].setdefault('extras',{})['inspection_composition']={'scope':'Explicit panel/texture candidate, no runtime installation; collision and detectors unchanged','panel_source_face_id':a.panel,'textured_logo':a.texture};data=compact(doc,data);write_glb(a.out/'base-visual.glb',doc,data);doc,data=read_glb(a.out/'base-visual.glb');checked=0;leds=0
    for x,y in zip(before['nodes'],doc['nodes']):
        if {k:v for k,v in x.items() if k!='mesh'}!={k:v for k,v in y.items() if k!='mesh'}:raise ValueError('source node metadata changed')
        if 'mesh' not in x:continue
        previous=old.payload(before,blob,x,True)
        # Texture materials lack a source diffuse triplet; these two selected
        # source members have no lights. Other members must match exactly.
        if x.get('extras',{}).get('source_unit_id') not in changed:
            if not old.equal(old.payload(before,blob,x),old.payload(doc,data,y)):raise ValueError('unselected rendered data changed')
            checked+=1;leds+=sum(len(p[0])//3 for p in previous)
        elif previous:raise ValueError('cannot replace a member containing lights')
    expected_count=68080-(10494-optimization['after_triangles'] if a.panel else 0)-(8893-report['after_housing_triangles'] if a.texture else 0)
    if scene_triangles(doc)!=expected_count:raise ValueError('composed count mismatch')
    result={'source_sha256':digest(source),'base_glb_sha256':digest(a.out/'base-visual.glb'),'before_triangles':68080,'after_triangles':scene_triangles(doc),'base_glb_bytes':(a.out/'base-visual.glb').stat().st_size,'exact_unselected_members':checked,'exact_light_triangles':leds,'collision_triangles_unchanged':16857,'panel_face_id':a.panel,'texture':a.texture,'producer_sha256':digest(Path(__file__))};(a.out/'composition.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':main()
