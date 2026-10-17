#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check exported protected attributes and render Rune LOD in its source pose."""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from run import module
from export_field_package import GlbWriter
from plan_cad_lods import build_plan,digest

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());source=ROOT/'out/rmuc2027-equipment-pipeline'
    structural=module('structural',ROOT/'benchmarks/2026-10-17-equipment-structure/review.py');loader=module('loader',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py')
    poses={}
    for n in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes']:
        if n['component_id']:poses.setdefault(n['component_id'],np.array(n['world_matrix_mm']))
    rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])@poses[summary['components'][0]['id']][:3,:3];display=np.eye(4);display[:3,:3]=rotation
    pieces={'before':[],'after':[]};selected={};checks=[]
    for change in summary['components']:
        cid=change['id'];before=source/cid/'lod.glb';after=out/cid/'candidate.glb'
        if digest(before)!=change['approved_glb_sha256'] or digest(after)!=change['outputs_sha256']['candidate.glb']:raise ValueError('input changed')
        b=structural.payload(before);c=structural.payload(after);units={r['native_shell_index']:r for r in change['units']};exact=0
        if set(b)!=set(c):raise ValueError('shell ownership changed')
        for unit,parts in b.items():
            for key,(data,colour,count) in parts.items():
                if not units[unit]['changed'] or colour is None or np.ptp(colour)>.1:
                    if key not in c[unit] or not np.array_equal(data,c[unit][key][0]):raise ValueError(f'protected payload changed: {cid}/{unit}')
                    exact+=count
        checks.append({'id':cid,'exact_protected_or_unmodified_triangles':exact})
        for stage,path in [('before',before),('after',after)]:
            data=loader.load(path);data=(data[0]@rotation.T,data[1],data[2]);pieces[stage].append(data)
            if cid in ['rune/banks/bank-a/arm-0','rune/support-and-shared']:selected.setdefault(cid.split('/')[-1],{})[stage]=data
    whole={stage:tuple(np.concatenate([p[k] for p in rows]) for k in range(3)) for stage,rows in pieces.items()};selected['whole']=whole
    for stage in ['before','after']:
        writer=GlbWriter('Rune '+stage,{'version':'2.0','copyright':'DJI / RoboMaster source geometry and appearance'})
        for change in summary['components']:
            cid=change['id'];path=(source/cid/'lod.npz') if stage=='before' else out/cid/'candidate.npz';mesh=np.load(path);palette=[v or None for v in mesh['palette'].tolist()]
            for unit in np.unique(mesh['unit_ids']):
                ids=mesh['unit_ids']==unit;used,inv=np.unique(mesh['triangles'][ids],return_inverse=True);writer.add_node(cid+'/shell-'+str(unit),mesh['positions_mm'][used]/1000,inv.reshape(-1,3),[palette[k] for k in mesh['material_ids'][ids]],matrix=display,extras={'component_id':cid,'native_shell_index':int(unit),'inspection_only':True})
        writer.write(out/('rune-'+stage+'.glb'))
    views={'oblique':(1,.5,1),'reverse':(-1,.5,-1),'front':(0,0,1),'back':(0,0,-1),'side':(1,0,0),'top':(0,1,.000001)};tests=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for scope,versions in selected.items():
            folder=out/'review'/scope;folder.mkdir(parents=True,exist_ok=True)
            for name,view in views.items():
                frames={stage:raster.raster(data[0],data[1],versions['before'][0],view,helper,tmp,folder/(stage+'-'+name+'.png')) for stage,data in versions.items()}
                measured=metrics.metric(frames['before'],frames['after'])
                masks=[(v[:,:,2]>80)&(v[:,:,0]<30)&(v[:,:,1]<30) for v in [frames['before'],frames['after']]]
                x,y=masks;measured['blue']={'before_pixels':int(x.sum()),'after_pixels':int(y.sum()),'lost_pixels':int((x&~y).sum()),'gained_pixels':int((y&~x).sum()),'difference_relative_fraction':float((x!=y).sum()/max(1,x.sum()))}
                tests.append({'scope':scope,'view':name,**measured})
    report={'before':summary['before'],'after':summary['after'],'saving':summary['before']-summary['after'],'previous_composed_field_triangles':2669054,'candidate_composed_field_triangles':2669054-summary['before']+summary['after'],'checks':checks,'views':tests,'producer_sha256':digest(Path(__file__)),'scope':'Exact exported protected/unmodified positions, normals and material attributes; 18 matched flat source-colour views. No runtime PBR, collision, moving-pose or continuous distance certification.'};(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['checks','views']},indent=2))
if __name__=='__main__':main()
