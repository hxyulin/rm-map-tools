#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""User-approved open-back Rune skins, selected independently per moving part."""
import argparse,importlib.util,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_visibility_skin import directional_skin,hemisphere_views,raster_owners
from plan_cad_lods import digest

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def front_direction(source,bank):
    """Use the authored front hub logo's area-weighted outward normal."""
    d=np.load(source/f'rune/banks/{bank}/hub-cluster/lod.npz');rgb=[np.ptp(list(map(float,c.split(','))))>.1 if c else False for c in d['palette']];ids=np.array(rgb)[d['material_ids']];g=d['positions_mm'][d['triangles'][ids]];cross=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);v=cross.sum(0)
    if np.linalg.norm(v)<1:raise ValueError('no unambiguous front logo normal')
    return v/np.linalg.norm(v)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--id');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    prior_dir=ROOT/'out/rmuc2027-rune-detail';prior=json.loads((prior_dir/'summary.json').read_bytes());source=ROOT/'out/rmuc2027-equipment-pipeline';pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');results=[];fronts={b:front_direction(source,b) for b in ['bank-a','bank-b']}
    with tempfile.TemporaryDirectory() as temporary:
        tmp=Path(temporary);helper=tmp/'raster';raster_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp';subprocess.run([shutil.which('clang++'),'-O3',str(raster_source),'-o',str(helper)],check=True)
        for previous in prior['components']:
            cid=previous['id']
            if a.id and cid!=a.id:continue
            folder=prior_dir/cid;target=a.out/cid;target.mkdir(parents=True,exist_ok=True)
            if digest(folder/'candidate.npz')!=previous['outputs_sha256']['candidate.npz']:raise ValueError('LOD input changed')
            d=np.load(folder/'candidate.npz');p=d['positions_mm'];t=d['triangles'];m=d['material_ids'];u=d['unit_ids'];palette=[v or None for v in d['palette'].tolist()];keep=np.arange(len(t));proof={'scope':'Support frame retained unchanged.'}
            if '/banks/' in cid:
                bank=cid.split('/')[2];front=fronts[bank];views=hemisphere_views(front);seen=set()
                for view in views:seen.update(map(int,raster_owners(p[t],view,helper,tmp)))
                keep,proof=directional_skin(p,t,m,u,front,np.array(sorted(seen),dtype=np.int64));proof.update({'front_direction':front.tolist(),'front_source':'Area-weighted chromatic front hub-logo normal in pinned source-local frame.','view_directions':views.tolist(),'resolution':2048})
            if not len(keep):raise ValueError('empty skin')
            used,inv=np.unique(t[keep],return_inverse=True);pipeline.save_mesh(target,'candidate',p[used],inv.reshape(-1,3),m[keep],palette,u[keep]);np.save(target/'retained-triangle-indices.npy',keep)
            result={'id':cid,'before':previous['after'],'after':len(keep),'reference_glb_sha256':previous['outputs_sha256']['candidate.glb'],'reference_npz_sha256':previous['outputs_sha256']['candidate.npz'],'original_source_step_sha256':previous['source_step_sha256'],'selection':proof,'outputs_sha256':{n:digest(target/n) for n in ['candidate.glb','candidate.npz','retained-triangle-indices.npy']}};results.append(result);print(cid,len(t),'->',len(keep),flush=True)
    report={'components':results,'before':sum(r['before'] for r in results),'after':sum(r['after'] for r in results),'previous_summary_sha256':digest(prior_dir/'summary.json'),'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_visibility_skin.py',raster_source]},'scope':'User-authorized open-back, directionally sampled visual skins for individual Rune arms/hubs. Separate parts cannot occlude each other during selection. Support frame unchanged. Deliberate rear/interior removal, not all-view equivalence or collision. Source CAD, installed assets and detectors unchanged.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
