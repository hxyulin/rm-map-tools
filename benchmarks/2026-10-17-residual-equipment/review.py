#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verify residual export attributes and render selected parts plus full equipment."""
import argparse,json,math,shutil,subprocess,tempfile
from pathlib import Path
from audit import ROOT,TARGETS,module
import numpy as np
from PIL import Image
from plan_cad_lods import digest,build_plan
from gltf_scene import read_glb,accessor


def exact_attributes(out,source_summary,skin_summary):
    payload=module('attributes',ROOT/'benchmarks/2026-10-17-equipment-structure/review.py').payload;results=[]
    source={r['id']:r for r in source_summary['components']}
    for row in skin_summary['components']:
        cid=row['id'];prior=source[cid];before=ROOT/'out/rmuc2027-composed-pipeline'/cid/'candidate.glb';detail=out/cid/'detail.glb';after=out/cid/'skin.glb'
        if digest(before)!=prior['reference_glb_sha256'] or digest(detail)!=prior['outputs_sha256']['detail.glb'] or digest(after)!=row['outputs_sha256']['skin.glb']:raise ValueError('export checksum changed')
        b=payload(before);d=payload(detail);f=payload(after);final=payload(out/cid/'final.glb');unchanged=[r['unit'] for r in prior['units'] if not r['selected_for_source_detail']];exact=0
        for unit in unchanged:
            if b[unit].keys()!=d[unit].keys() or b[unit].keys()!=f[unit].keys() or b[unit].keys()!=final[unit].keys():raise ValueError('unselected shell material changed')
            for key in b[unit]:
                if not np.array_equal(b[unit][key][0],d[unit][key][0]) or not np.array_equal(b[unit][key][0],f[unit][key][0]) or not np.array_equal(b[unit][key][0],final[unit][key][0]):raise ValueError('unselected shell positions/normals/materials changed')
                exact+=b[unit][key][2]
        # Skin is an exact triangle subset, checked against the actual detail GLB.
        mesh=np.load(out/cid/'detail.npz');ids={r['unit']:np.array(r['retained_input_triangle_indices'],int) for r in row['units']}
        for unit,items in f.items():
            for key,(packed,colour,count) in items.items():
                if key not in d[unit] or not np.all(np.isin(packed,d[unit][key][0])):raise ValueError('skin exported attributes are not exact input subset')
        for unit in f:
            if cid=='technology-core/tool-head' and unit==4:continue
            if f[unit].keys()!=final[unit].keys() or any(not np.array_equal(f[unit][key][0],final[unit][key][0]) for key in f[unit]):raise ValueError('final override changed another shell')
        results.append({'id':cid,'unselected_shells_exact':len(unchanged),'unselected_exported_triangles_exact':exact,'skin_exported_attributes_exact_subset':True})
    return results


def save_sheet(images,path):
    sheet=Image.new('RGB',(len(images)*600,600))
    for i,img in enumerate(images):sheet.paste(Image.fromarray(img).resize((600,600),Image.Resampling.LANCZOS),(i*600,0))
    sheet.save(path,lossless=True,method=4)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());skin=json.loads((out/'skin-summary.json').read_bytes());final=json.loads((out/'final-summary.json').read_bytes());audit=json.loads((out/'audit.json').read_bytes());audit_by={r['id']:r for r in audit['components']};attribute_checks=exact_attributes(out,summary,skin)
    loader=module('loader',ROOT/'benchmarks/2026-10-17-equipment-pipeline/review.py');raster=module('raster',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py');scene=module('scene',ROOT/'benchmarks/2026-10-17-composed-pipeline/review.py');texture_raster=module('texture_raster',ROOT/'benchmarks/2026-10-17-base-panel-textures/review.py');poses={}
    for n in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes']:
        if n['component_id']:poses.setdefault(n['component_id'],np.array(n['world_matrix_mm']))
    entries=[]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for row in final['components']:
            cid=row['id'];folder=out/cid;paths={'before':ROOT/'out/rmuc2027-composed-pipeline'/cid/'candidate.glb','planar':folder/'planar.glb','detail':folder/'detail.glb','final':folder/'final.glb'};rotation=np.array([[1,0,0],[0,0,1],[0,-1,0]])@poses[cid][:3,:3];data={stage:loader.load(path) for stage,path in paths.items()};data={stage:(g@rotation.T,c,u) for stage,(g,c,u) in data.items()}
            scopes=[('component',None)]
            specific={'rune/banks/bank-a/hub-cluster':[18,19],'rune/banks/bank-b/hub-cluster':[18,19],'rune/support-and-shared':[15,20,37,45,62,78],'resource-area/mechanism':[4,29],'technology-core/tool-head':[4,33,1211]}
            scopes.extend(('shell-'+str(unit),unit) for unit in specific[cid])
            for name,unit in scopes:
                chosen=data if unit is None else {s:(g[u==unit],c[u==unit],u[u==unit]) for s,(g,c,u) in data.items()}
                if unit is None:normal=np.array([0,.000001,1])
                else:
                    planes=next(u for u in audit_by[cid]['units'] if u['unit']==unit)['largest_native_planes'];normal=rotation@np.array(planes[0]['normal']) if planes else np.array([0,.000001,1])
                views=[('oblique',(1,.6,1.5)),('reverse',(-1,.6,-1.5)),('front',normal),('back',-normal),('top',(0,1,.000001)),('bottom',(0,-1,.000001))]
                images=folder/'review'/name;images.mkdir(parents=True,exist_ok=True);checks=[]
                for view_name,view in views:
                    frames={s:raster.raster(g,c,chosen['before'][0],view,helper,tmp,images/(s+'-'+view_name+'.png')) for s,(g,c,u) in chosen.items()}
                    save_sheet(list(frames.values()),images/(view_name+'.webp'))
                    for stage in ['planar','detail','final']:checks.append({'stage':stage,'view':view_name,**metrics.metric(frames['before'],frames[stage])})
                entries.append({'id':cid+'/'+name,'component_id':cid,'scope':name,'views':checks,'view_names':[v[0] for v in views],'triangles':{stage:len(d[0]) for stage,d in chosen.items()},'images':str(images.relative_to(out))});print('reviewed',cid,name,entries[-1]['triangles'],flush=True)
        # Complete equipment uses the actual composed scene, including unchanged components.
        helper=tmp/'texture-raster';subprocess.run([shutil.which('clang++'),'-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        full={};owners={}
        for stage in ['reference','candidate']:full[stage],owners[stage]=scene.load_scene(out/(stage+'-field.glb'))
        for group in ['field','rune','resource-area','technology-core']:
            if group=='field':data=full
            else:
                first=next(v for v in owners['reference'].values() if v['component_id'].startswith(group+'/'));g=full['reference'][0][full['reference'][4]==first['index']];anchor=(g.min((0,1))+g.max((0,1)))/2;data={stage:scene.select(d,owners[stage],group,anchor) for stage,d in full.items()}
            folder=out/'review'/('complete-'+group);folder.mkdir(parents=True,exist_ok=True);checks=[];views=[('oblique',(1,1.2 if group=='field' else .6,1.5)),('reverse',(-1,1.2 if group=='field' else .6,-1.5)),('top',(0,1,.000001))]
            if group!='field':views.extend([('front',(0,.000001,1)),('back',(0,.000001,-1)),('bottom',(0,-1,.000001))])
            for name,view in views:
                frames={stage:texture_raster.raster(d,data['reference'][0],view,helper,tmp,folder/(stage+'-'+name+'.png')) for stage,d in data.items()};save_sheet(list(frames.values()),folder/(name+'.webp'));checks.append({'stage':'final','view':name,**metrics.metric(frames['reference'],frames['candidate'])})
            entries.append({'id':'complete-'+group,'component_id':None,'scope':'complete','views':checks,'view_names':[v[0] for v in views],'triangles':{'before':len(data['reference'][0]),'final':len(data['candidate'][0])},'images':str(folder.relative_to(out))});print('reviewed complete',group,entries[-1]['triangles'],flush=True)
    report={'entries':entries,'exported_attributes':attribute_checks,'source_summary_sha256':digest(out/'summary.json'),'skin_summary_sha256':digest(out/'skin-summary.json'),'final_summary_sha256':digest(out/'final-summary.json'),'assembly_sha256':digest(out/'assembly.json'),'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'benchmarks/2026-10-17-composed-pipeline/review.py',ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp']},'scope':'Actual GLB attributes, matched six-view work-part and selected-shell checks, plus complete source-pose equipment/field. Two-sided flat colors and embedded artwork. No runtime PBR, continuous visibility/error or moving-pose guarantee.'};(out/'review.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
