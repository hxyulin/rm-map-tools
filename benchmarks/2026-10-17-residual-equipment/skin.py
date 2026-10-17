#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Trial conservative full-sphere skin selection inside explicitly selected shells."""
import argparse,itertools,json,math,shutil,subprocess,tempfile
from pathlib import Path
from run import ROOT,TARGETS,POLICIES,module,join
import numpy as np
from cad_pass_composition import subset
from cad_visibility_skin import raster_owners,all_view_skin
from plan_cad_lods import digest


def views():
    return [np.array(v,float)/np.linalg.norm(v) for v in itertools.product([-1,0,1],repeat=3) if any(v)]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();source_summary=a.out/'summary.json';summary=json.loads(source_summary.read_bytes());pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');results=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for row in summary['components']:
            cid=row['id'];folder=a.out/cid;path=folder/'detail.npz'
            if digest(path)!=row['outputs_sha256']['detail.npz']:raise ValueError('detail reference changed')
            mesh=dict(np.load(path));palette=[v or None for v in mesh['palette'].tolist()];parts=[];records=[]
            for unit in np.unique(mesh['unit_ids']):
                p,t,m=subset(mesh,mesh['unit_ids']==unit);keep=np.arange(len(t));proof=None
                if int(unit) in POLICIES[cid] and len(t)>=128:
                    observed=set()
                    for view in views():observed.update(map(int,raster_owners(p[t],view,helper,tmp,resolution=1024)))
                    keep,proof=all_view_skin(p,t,m,np.array(sorted(observed),dtype=np.int64));checks=[]
                    # Independent directions and 1200px color shading, never used as selection views.
                    for view in [(1,.37,1.6),(-1,.37,-1.6),(.3,1,.7),(.3,-1,-.7),(-.7,.23,1),(.7,-.23,-1)]:
                        old=raster.raster(p[t]/1000,np.array([[.6275]*3 if palette[k] is None else list(map(float,palette[k].split(','))) for k in m]),p[t]/1000,view,helper,tmp)
                        new=raster.raster(p[t[keep]]/1000,np.array([[.6275]*3 if palette[k] is None else list(map(float,palette[k].split(','))) for k in m[keep]]),p[t]/1000,view,helper,tmp)
                        checks.append(metrics.metric(old,new))
                    maximum=max(c['foreground_difference_relative_fraction'] for c in checks);rgb=max(c['rgb_changed_over_10_fraction'] for c in checks)
                    accepted=maximum<=.0002 and rgb<=.001
                    proof.update(independent_views=checks,maximum_foreground_difference=maximum,maximum_rgb_changed_over_10_fraction=rgb,accepted=accepted)
                    if not accepted:keep=np.arange(len(t))
                    print(cid,'unit',unit,len(t),'->',len(keep),'skin accepted',accepted,flush=True)
                parts.append((p,t[keep],m[keep],int(unit)));records.append({'unit':int(unit),'before':len(t),'after':len(keep),'skin':proof,'retained_input_triangle_indices':keep.tolist()})
            p,t,m,u=join(parts);pipeline.save_mesh(folder,'skin',p,t,m,palette,u)
            record={'id':cid,'uses':row['uses'],'before':row['before'],'detail':row['detail'],'after':len(t),'units':records,'reference_npz_sha256':digest(path),'source_step_sha256':row['source_step_sha256'],'outputs_sha256':{name:digest(folder/name) for name in ['skin.glb','skin.npz']}};results.append(record);print('SKIN',cid,row['before'],'->',len(t),flush=True)
    report={'components':results,'reference_summary_sha256':digest(source_summary),'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_visibility_skin.py']},'placed_saving':sum((r['before']-r['after'])*r['uses'] for r in results),'scope':'Optional full-sphere raster-selected skin inside each selected rigid shell. Complete planar patches and one neighbor ring retained. Six independent held-out unit views admit only <=0.02% foreground and <=0.1% whole-image RGB change; otherwise whole shell retains detail geometry. Never cull between independently owned shells. Finite diagnostics only, no collision/runtime change.'};report['candidate_field_placed_triangles']=1573606-report['placed_saving'];(a.out/'skin-summary.json').write_text(json.dumps(report,indent=2)+'\n');print('TOTAL',report['placed_saving'],report['candidate_field_placed_triangles'],flush=True)
if __name__=='__main__':main()
