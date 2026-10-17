#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check actual omitted surfaces, optical attributes and projectile-clear ports."""
import argparse
import json
from pathlib import Path
import sys
from common import ROOT,module,read_mesh
import numpy as np
from cad_component_detail import connected_pieces
from cad_dense_lod import surface_samples
from gltf_scene import read_glb,accessor,scene_nodes
from mesh_quality import distances
from plan_cad_lods import digest


def channels(path):
    d,b=read_glb(path);positions=[];normals=[];materials=[];units=[]
    for node,world,_ in scene_nodes(d):
        n=d['nodes'][node]
        if 'mesh'not in n:continue
        owner=n['extras'].get('source_native_shell_index',n['extras'].get('native_shell_index'))
        for prim in d['meshes'][n['mesh']]['primitives']:
            t=accessor(d,b,prim['indices']).reshape(-1,3)
            if np.linalg.det(world[:3,:3])<0:t=t[:,[0,2,1]]
            p=accessor(d,b,prim['attributes']['POSITION']).astype(float)@world[:3,:3].T+world[:3,3];positions.append(p[t]*1000);normals.append(accessor(d,b,prim['attributes']['NORMAL'])[t]);materials.extend([prim['material']]*len(t));units.extend([owner]*len(t))
    return np.concatenate(positions),np.concatenate(normals),np.array(materials),np.array(units),d['materials']


def optical(g,m,materials,units,excluded=()):
    result={}
    for key in np.unique(m):
        color=materials[key]['extras']['step_colour_srgb']
        mask=m==key
        for unit,material in excluded:
            if key==material:mask&=units!=unit
        if color and np.ptp(color)>.1:result[int(key)]=sorted(map(tuple,g[mask].reshape(-1,9)))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();details=json.loads((out/'detail-summary.json').read_bytes());prior=ROOT/'out/rmuc2027-dart-outpost';ledger=json.loads((prior/'summary.json').read_bytes());by={r['id']:r for r in ledger['components']};openings=json.loads((prior/'validation.json').read_bytes());ports={r['id']:r.get('qualified_opening_paths',[])for r in openings['components']}
    if digest(prior/'validation.json')!=details['port_validation_sha256']:raise ValueError('qualified source ports changed')
    sys.path.insert(0,str(ROOT/'benchmarks/2026-10-17-collision-solids'));check=module('contact_check',ROOT/'benchmarks/2026-10-17-collision-solids/validate.py');results=[]
    for r in details['components']:
        cid=r['id'];folder=out/cid;source=ROOT/by[cid]['visual_glb'];old=read_mesh(source);p,t,m,u=[old[k]for k in ['positions_mm','triangles','material_ids','unit_ids']];keep=np.ones(len(t),bool);removed_pieces=0;maximum_backing=0
        for record in r['detail_members']:
            ids=np.flatnonzero(u==record['source_member']);labels=connected_pieces(p,t[ids]);omitted=[]
            for part in record['detail']['pieces']:
                if not part['removed']:continue
                if part['protected']or max(part['span_mm'])>=17 or part['maximum_backing_distance_mm']>=17:raise ValueError('invalid detail omission')
                omitted.append(part['piece']);maximum_backing=max(maximum_backing,part['maximum_backing_distance_mm']);removed_pieces+=1
            keep[ids[np.isin(labels,omitted)]]=False
        before=channels(source);micro=channels(folder/'micro.glb');current=channels(folder/'visual.glb')
        for i in range(4):
            if not np.array_equal(before[i][keep],micro[i]):raise ValueError('micro stage changed retained source attributes '+cid+' channel '+str(i))
        if before[4]!=micro[4]or before[4]!=current[4]:raise ValueError('source PBR materials changed')
        excluded=[]
        if r.get('end_cap_envelopes'):
            cap=r['end_cap_envelopes'];excluded=[(cap['source_member'],cap['source_material_id'])]
            if digest(folder/'caps-before.glb')!=cap['input_visual_sha256']or digest(ROOT/'python/cad_profile_envelope.py')!=cap['pass_sha256']:raise ValueError('cap profile inputs changed')
        if optical(before[0],before[2],before[4],before[3],excluded)!=optical(current[0],current[2],current[4],current[3],excluded):raise ValueError('colored optical triangles changed')
        mesh=np.load(folder/'contact.npz');cp,ct,cu=check.exported(folder/'contact.glb',mesh);contact=read_mesh(folder/'contact.glb');visual=read_mesh(folder/'visual.glb');source_samples=surface_samples(p,t).reshape(-1,3);quality={}
        for stage,d in [('visual',visual),('collision',contact)]:
            q,f=d['positions_mm'],d['triangles'];forward=distances(source_samples,q,f);reverse=distances(surface_samples(q,f).reshape(-1,3),p,t);worst=float(max(forward.max(),reverse.max()))
            if worst>17.005:raise ValueError('end-to-end detail budget exceeded '+cid+' '+stage+' '+str(worst))
            quality[stage]={'all_triangle_samples':len(forward)+len(reverse),'maximum_source_to_candidate_mm':float(forward.max()),'maximum_candidate_to_source_mm':float(reverse.max())}
        paths=[]
        for path in ports.get(cid,[]):
            owner=path['source_member'];start,end=np.array([path['start_mm'],path['end_mm']]);faces=ct[cu==owner]
            if not len(faces):raise ValueError('protected port owner omitted')
            hit=check.raycaster(cp,faces)(start,end)
            if hit is not None:raise ValueError('source-qualified opening center filled '+cid)
            centers=np.linspace(start,end,129);clearance=float(distances(centers,cp,faces).min());bound=clearance-float(np.linalg.norm(end-start))/256
            if bound<8.495:raise ValueError('17 mm port clearance lost '+cid+' '+str(bound))
            paths.append({**path,'minimum_candidate_surface_clearance_mm':clearance,'segment_clearance_lower_bound_mm':bound,'center_samples':129})
        result={'id':cid,'reference_triangles':len(t),'micro_triangles':len(micro[0]),'visual_triangles':len(current[0]),'collision_triangles':len(ct),'omitted_pieces':removed_pieces,'omitted_triangles':int((~keep).sum()),'maximum_omitted_piece_backing_distance_mm':maximum_backing,'retained_micro_positions_normals_materials_owners_exact':True,'optical_triangle_positions_and_pbr_exact':True,'source_step_sha256':digest(ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step'),'source_visual_sha256':digest(source),'quality':quality,'qualified_opening_paths':paths,'output_sha256':{name:digest(folder/name)for name in ['micro.glb','visual.glb','contact.glb','contact.npz']}}
        results.append(result);print(cid,'omitted',result['omitted_triangles'],'visual max mm',quality['visual']['maximum_source_to_candidate_mm'],'ports',len(paths),flush=True)
    (out/'validation.json').write_text(json.dumps({'components':results,'detail_summary_sha256':digest(out/'detail-summary.json'),'producer_sha256':digest(__file__),'scope':'Actual exported source-subset attribute equality, exact optical positions/PBR, source-to-final all-triangle samples under 17 mm, exact contact payload/owners, and mesh-segment 17 mm sphere clearance on earlier source-qualified ports. No all-trajectory, source-solid, new-motion or runtime binding claim.'},indent=2)+'\n')


if __name__=='__main__':main()
