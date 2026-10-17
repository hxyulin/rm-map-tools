#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Selective Rune LOD; source CAD and coloured/unstyled triangles stay intact."""
import argparse, importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_local_lod import guarded_vertex_lod
from mesh_quality import deviation, distances
from plan_cad_lods import digest

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');record=module('record',ROOT/'benchmarks/2026-10-17-equipment-pipeline/record.py')
    source=ROOT/'out/rmuc2027-equipment-pipeline';ledger=json.loads((source/'passes.json').read_bytes());results=[]
    for prior in ledger['components']:
        cid=prior['id']
        if not cid.startswith('rune/'):continue
        folder=source/cid;target=a.out/cid;target.mkdir(parents=True,exist_ok=True)
        if digest(folder/'native.npz')!=prior['native_npz_sha256'] or digest(folder/'source.step')!=prior['source_step_sha256'] or digest(folder/'lod.glb')!=prior['outputs_sha256']['lod.glb']:raise ValueError('pinned input changed')
        native=np.load(folder/'native.npz');base=np.load(folder/'lod.npz');palette=[v or None for v in native['palette'].tolist()];protected=[i for i,c in enumerate(palette) if c is None or np.ptp(list(map(float,c.split(','))))>.1]
        chromatic=[i for i,c in enumerate(palette) if c is not None and np.ptp(list(map(float,c.split(','))))>.1]
        colour_faces=native['triangles'][np.isin(native['material_ids'],chromatic)]
        pp=[];tt=[];mm=[];uu=[];offset=0;rows=[]
        for unit in np.unique(base['unit_ids']):
            ids=native['unit_ids']==unit;used,inv=np.unique(native['triangles'][ids],return_inverse=True);p=native['positions_mm'][used];t=inv.reshape(-1,3);m=native['material_ids'][ids]
            bid=base['unit_ids']==unit;bu,bi=np.unique(base['triangles'][bid],return_inverse=True);bp=base['positions_mm'][bu];bt=bi.reshape(-1,3);bm=base['material_ids'][bid];count=len(bt)
            eligible=~np.isin(m,protected);span=float(np.ptp(p,axis=0).max());proof=None;quality=None
            if eligible.any():
                small=span<=17;limit=.4 if small else 3;metric=.15 if small else 1
                # Lock original material boundaries, retain protected source faces exactly.
                locks=np.unique(t[~eligible])
                if not small and len(colour_faces):locks=np.union1d(locks,np.flatnonzero(distances(p,native['positions_mm'],colour_faces)<=5))
                q,f,k,proof=guarded_vertex_lod(p,t,m,error_mm=metric,sampled_limit_mm=limit,sample_count=2048 if small else 16384,maximum_iterations=8,protected_vertex_indices=locks)
                keep=~np.isin(k,protected);f=np.concatenate([f[keep],t[~eligible]+len(q)]);k=np.r_[k[keep],m[~eligible]];q=np.concatenate([q,p]);quality=deviation(p,t,q,f,count=2048 if small else 32768)
                if len(f)<count and quality['max']<=limit+.001:bp,bt,bm=q,f,k
            changed=len(bt)<count
            pp.append(bp);tt.append(bt+offset);mm.append(bm);uu.append(np.full(len(bt),unit));offset+=len(bp)
            rows.append({'native_shell_index':int(unit),'span_mm':span,'before':count,'after':len(bt),'changed':changed,'sampled_deviation_mm':quality if changed else None,'guard':record.compact(proof) if changed else None})
        pipeline.save_mesh(target,'candidate',np.concatenate(pp),np.concatenate(tt),np.concatenate(mm),palette,np.concatenate(uu))
        result={'id':cid,'source_step_sha256':prior['source_step_sha256'],'native_npz_sha256':prior['native_npz_sha256'],'approved_glb_sha256':digest(folder/'lod.glb'),'before':len(base['triangles']),'after':sum(len(v) for v in tt),'protected_material_ids':protected,'units':rows,'outputs_sha256':{name:digest(target/name) for name in ['candidate.glb','candidate.npz']}}
        results.append(result);(target/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(cid,result['before'],'->',result['after'],flush=True)
    report={'components':results,'before':sum(r['before'] for r in results),'after':sum(r['after'] for r in results),'producer_sha256':digest(Path(__file__)),'scope':'Native-reference per-shell LOD, .15mm nominal/.4mm sampled for shells <=17mm; 1mm nominal/3mm sampled otherwise. Never adopt a triangle increase. Coloured and unresolved faces preserved; neutral vertices within 5mm of chromatic source surfaces locked. No shell removal, native topology edits, collision or runtime replacement; finite samples are not continuous bounds.'}
    (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
