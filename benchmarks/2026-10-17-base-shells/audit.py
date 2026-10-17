#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only Base shell visibility/coplanarity audit; visibility is sampled."""
import argparse,importlib.util,json,math,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,accessor
from plan_cad_lods import digest
spec=importlib.util.spec_from_file_location('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');render=importlib.util.module_from_spec(spec);spec.loader.exec_module(render)
TARGETS=[4268930,4527988,4314593,4353403,4392221,4594338,4664029,4693907,4723785,4756187,4764759]

def load(path):
    doc,blob=read_glb(path);pp=[];cc=[];uu=[];nn=[];audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());lookup={u['source_id']:i for i,u in enumerate(audit['units'])}
    for n in doc['nodes']:
        if 'mesh' not in n:continue
        if any(k in n for k in ['matrix','translation','rotation','scale']):raise ValueError('requires baked member positions')
        source=n['extras']['source_unit_id'];index=lookup[source]
        for p in doc['meshes'][n['mesh']]['primitives']:
            t=accessor(doc,blob,p['indices']).reshape(-1,3);pp.append(accessor(doc,blob,p['attributes']['POSITION'])[t].astype(float)*1000);nn.append(accessor(doc,blob,p['attributes']['NORMAL'])[t]);cc.extend([doc['materials'][p['material']]['extras']['step_colour_srgb']]*len(t));uu.extend([index]*len(t))
    g=np.concatenate(pp);npz={'positions_mm':g.reshape(-1,3),'triangles':np.arange(len(g)*3).reshape(-1,3),'triangle_srgb':np.asarray(cc),'unit_ids':np.asarray(uu,dtype=np.uint32),'source_face_ids':np.zeros(len(g),dtype=np.uint32),'triangle_vertex_normals':np.concatenate(nn)}
    return npz,audit

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(exist_ok=True,parents=True);source=ROOT/'out/rmuc2027-base-aggressive-final/base-visual.glb';d,audit=load(source);np.savez(a.out/'baseline.npz',**d);g=d['positions_mm'][d['triangles']]/1000;c=d['triangle_srgb'];ids=d['unit_ids'];report={'source_sha256':digest(source),'units':[],'scope':'Pixel-sampled isolated/assembled visibility is an audit, not permission to delete surfaces.'};directions=[]
    for el in [-60,-30,0,30,60]:
        for az in range(0,360,30):
            az=math.radians(az);e=math.radians(el);directions.append((math.cos(az)*math.cos(e),math.sin(e),math.sin(az)*math.cos(e)))
    directions.extend([(0,1,.000001),(0,-1,.000001)])
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True);whole_seen=np.zeros(len(g),bool)
        for view in directions:
            render.raster(g,c,g,view,helper,tmp);owners=np.fromfile(tmp/'owners.bin',dtype=np.int32);whole_seen[owners[owners>=0]]=True
        for source_id in TARGETS:
            i=next(i for i,u in enumerate(audit['units']) if u['source_id']==source_id);mask=ids==i;xyz=g[mask];col=c[mask];seen=np.zeros(len(xyz),bool)
            for k,view in enumerate(directions):
                render.raster(xyz,col,xyz,view,helper,tmp,a.out/f'{source_id}-{k}.png' if k in [27,32,39,60,61] else None);owners=np.fromfile(tmp/'owners.bin',dtype=np.int32);seen[owners[owners>=0]]=True
            normal=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]);area=np.linalg.norm(normal,axis=1);normal/=np.maximum(area[:,None],1e-30);normal*=np.where(normal[np.arange(len(normal)),np.argmax(abs(normal),axis=1)]<0,-1,1)[:,None];plane=np.c_[normal,np.sum(normal*xyz[:,0],axis=1)*1000];_,inv,count=np.unique(np.round(plane,3),axis=0,return_inverse=True,return_counts=True);top=np.argsort(count)[-12:][::-1];groups=[{'normal_offset_mm':np.round(plane[inv==j][0],3).tolist(),'triangles':int(count[j])} for j in top];r={'source_unit_id':source_id,'triangles':len(xyz),'isolated_seen_triangles':int(seen.sum()),'assembled_seen_triangles':int(whole_seen[mask].sum()),'isolated_unseen_area_fraction':float(area[~seen].sum()/area.sum()),'large_quantized_plane_groups':groups};report['units'].append(r);print(source_id,len(xyz),'isolated unseen',int((~seen).sum()),'assembled unseen',int((~whole_seen[mask]).sum()),'top planes',sum(x['triangles'] for x in groups),flush=True)
    report['producer_sha256']=digest(Path(__file__));(a.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
