#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Count the hierarchy, verify exported candidates, and render matched views."""
import argparse,collections,html,importlib.util,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,accessor
from plan_cad_lods import digest,build_plan
from export_field_package import GlbWriter
from mesh_quality import deviation

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def load(path):
    doc,blob=read_glb(path);xyz=[];col=[];units=[]
    for node in doc['nodes']:
        if 'mesh' not in node:continue
        if any(k in node for k in ['matrix','rotation','translation','scale']):raise ValueError('expected baked work-part mesh')
        for prim in doc['meshes'][node['mesh']]['primitives']:
            t=accessor(doc,blob,prim['indices']).reshape(-1,3);p=accessor(doc,blob,prim['attributes']['POSITION']);xyz.append(p[t]);material=doc['materials'][prim['material']];rgb=material['extras']['step_colour_srgb'] or [.6275,.6275,.6275];col.extend([rgb]*len(t));units.extend([node['extras']['native_shell_index']]*len(t))
    return np.concatenate(xyz).astype(float),np.array(col),np.array(units)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();inventory=json.loads((out/'inventory.json').read_bytes());passes=json.loads((out/'passes.json').read_bytes());groups=collections.defaultdict(list)
    for r in passes['components']:groups[r['id'].split('/')[0]].append(r)
    poses={}
    for node in build_plan(json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes()))['nodes']:
        if node['component_id']:poses.setdefault(node['component_id'],np.array(node['world_matrix_mm']))
    y_up=np.array([[1,0,0],[0,0,1],[0,-1,0]])
    distance_cache={};cache_path=out/'distance-checks.json'
    if cache_path.exists():
        cache=json.loads(cache_path.read_bytes())
        if cache['passes_sha256']==digest(out/'passes.json'):distance_cache={(r['id'],r['unit']):r['exported_sampled_deviation_mm'] for r in cache['checks']}
    render=module('render',ROOT/'benchmarks/2026-10-17-base-passes/validate_render.py');metrics=module('metrics',ROOT/'benchmarks/2026-10-17-base-housing-aggressive/review.py')
    report={'groups':[],'scope':'Complete 116-definition hierarchy inventory with original occurrence multiplicities. Native .4 mm/.25 rad; experimental visual replacements are listed explicitly. Six 1200² fixed source-pose diagnostic views per equipment group, not runtime PBR or motion validation.'}
    views=[('oblique',(1,.6,1.5)),('reverse',(-1,.6,-1.5)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('top',(0,1,.000001)),('bottom',(0,-1,.000001))]
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'),'-o',str(helper)],check=True)
        for group,rows in groups.items():
            data={};protected_count=0;final_checks=[];folder=out/'review'/group;folder.mkdir(parents=True,exist_ok=True)
            rotation=poses[rows[0]['id']][:3,:3]
            if any(not np.allclose(poses[r['id']][:3,:3],rotation,rtol=0,atol=1e-10) for r in rows):raise ValueError('mixed work-part orientations')
            display=np.eye(4);display[:3,:3]=y_up@rotation
            for stage in ['native','planar','lod']:
                pieces=[];writer=GlbWriter(group,{'version':'2.0','copyright':'DJI / RoboMaster source geometry; diagnostic visual candidate'})
                for r in rows:
                    path=out/r['id']/(stage+'.glb');expected=r['native_glb_sha256'] if stage=='native' else r['outputs_sha256'][stage+'.glb']
                    if digest(path)!=expected:raise ValueError('export changed')
                    d=load(path);expected_count=r['native_triangles'] if stage=='native' else r[stage+'_triangles']
                    if len(d[0])!=expected_count:raise ValueError('export count differs')
                    pieces.append(d)
                    mesh=np.load(out/r['id']/(stage+'.npz'));palette=[v or None for v in mesh['palette'].tolist()]
                    for unit in np.unique(mesh['unit_ids']):
                        ids=np.flatnonzero(mesh['unit_ids']==unit);t=mesh['triangles'][ids];used,inv=np.unique(t,return_inverse=True)
                        writer.add_node(r['id']+'/shell-'+str(unit),mesh['positions_mm'][used]/1000,inv.reshape(-1,3),[palette[k] for k in mesh['material_ids'][ids]],matrix=display,extras={'component_id':r['id'],'native_shell_index':int(unit),'inspection_only':True,'display_orientation':'first source occurrence rotation, converted to Y-up; translation omitted'})
                    if stage=='lod':
                        original=load(out/r['id']/'native.glb')
                        mask=lambda x:(np.ptp(x[1],axis=1)>.1)
                        # Compare rendered positions and source material for
                        # every chromatic triangle, independent of ordering.
                        encode=lambda x:sorted(map(tuple,np.c_[x[0][mask(x)].reshape(-1,9),x[1][mask(x)]]))
                        if encode(original)!=encode(d):raise ValueError('exported chromatic geometry changed')
                        protected_count+=int(mask(d).sum())
                        for unit in [q['unit'] for q in r['unit_checks']]:
                            old=original[0][original[2]==unit]*1000;new=d[0][d[2]==unit]*1000
                            quality=distance_cache.get((r['id'],unit))
                            if quality is None:quality=deviation(old.reshape(-1,3),np.arange(len(old)*3).reshape(-1,3),new.reshape(-1,3),np.arange(len(new)*3).reshape(-1,3),count=8192)
                            if quality['max']>1.001:raise ValueError('exported end-to-end unit guard failed: '+r['id']+' '+str(unit)+' '+str(quality))
                            final_checks.append({'id':r['id'],'unit':unit,'exported_sampled_deviation_mm':quality})
                data[stage]=tuple(np.concatenate([d[k] for d in pieces]) for k in range(3))
                data[stage]=(data[stage][0]@display[:3,:3].T,)+data[stage][1:]
                writer.write(folder/(stage+'.glb'))
            checks=[]
            for name,view in views:
                images={stage:render.raster(d[0],d[1],data['native'][0],view,helper,tmp,folder/(stage+'-'+name+'.png')) for stage,d in data.items()}
                for stage in ['planar','lod']:checks.append({'stage':stage,'view':name,**metrics.metric(images['native'],images[stage])})
            result={'group':group,'definitions':len(rows),'native_triangles':len(data['native'][0]),'planar_triangles':len(data['planar'][0]),'lod_triangles':len(data['lod'][0]),'native_placed_triangles':sum(r['uses']*r['native_triangles'] for r in rows),'planar_placed_triangles':sum(r['uses']*r['planar_triangles'] for r in rows),'lod_placed_triangles':sum(r['uses']*r['lod_triangles'] for r in rows),'exact_chromatic_triangles':protected_count,'exported_unit_checks':final_checks,'views':checks}
            report['groups'].append(result);print(group,result['native_triangles'],'->',result['lod_triangles'],flush=True)
    original=sum(r['native_triangles']*r['uses'] for r in inventory['components']);base=next(r for r in inventory['components'] if r['id']=='base/source-model');base_path=ROOT/'out/rmuc2027-base-textures-final/base-visual.glb';base_doc,base_blob=read_glb(base_path);base_count=sum(accessor(base_doc,base_blob,p['indices']).size//3 for n in base_doc['nodes'] if 'mesh' in n for p in base_doc['meshes'][n['mesh']]['primitives'])
    walls=json.loads((ROOT/'out/rmuc2027-wall-fill-final/summary.json').read_bytes())
    # Established wall replacement delta was independently placed and validated
    # in the terrain-density benchmark; do not count projected road savings.
    by_id={r['id']:r for r in inventory['components']}
    for wall in walls['components']:
        native=by_id[wall['component_id']]
        if native['native_triangles']!=wall['before']['triangles'] or native['uses']!=wall['placed_uses']:raise ValueError('wall inventory mismatch')
    wall_saving=walls['placed_triangles_before']-walls['placed_triangles_after']
    selected_before=sum(r['native_triangles']*r['uses'] for r in passes['components']);selected_after=sum(r['lod_triangles']*r['uses'] for r in passes['components']);selected_planar=sum(r['planar_triangles']*r['uses'] for r in passes['components'])
    report['totals']={'hierarchy_definitions':len(inventory['components']),'hierarchy_placed_work_parts':sum(r['uses'] for r in inventory['components']),'native_definition_triangles':sum(r['native_triangles'] for r in inventory['components']),'native_placed_triangles':original,'native_base_per_placement':base['native_triangles'],'approved_base_per_placement':base_count,'base_sha256':digest(base_path),'wall_fill_placed_saving':wall_saving,'before_other_equipment_trials_placed_triangles':original-base['uses']*(base['native_triangles']-base_count)-wall_saving,'equipment_native_placed_triangles':selected_before,'equipment_planar_placed_triangles':selected_planar,'equipment_lod_placed_triangles':selected_after,'equipment_lod_placed_saving':selected_before-selected_after,'combined_trial_placed_triangles':original-base['uses']*(base['native_triangles']-base_count)-wall_saving-(selected_before-selected_after),'road_preview_savings_included':False}
    report['input_sha256']={str(p.relative_to(ROOT)):digest(p) for p in [out/'inventory.json',out/'passes.json',ROOT/'out/rmuc2027-terrain-density/summary.json',ROOT/'out/rmuc2027-wall-fill-final/summary.json']};report['producer_sha256']={str(Path(__file__).relative_to(ROOT)):digest(Path(__file__))};(out/'review.json').write_text(json.dumps(report,indent=2)+'\n')
    cache_path.write_text(json.dumps({'passes_sha256':digest(out/'passes.json'),'checks':[r for group in report['groups'] for r in group['exported_unit_checks']]},indent=2)+'\n')
    print(json.dumps(report['totals'],indent=2))

if __name__=='__main__':main()
