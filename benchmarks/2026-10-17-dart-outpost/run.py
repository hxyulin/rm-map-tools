#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reduce source-owned Dart/Outpost details and prepare independent contact LODs."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_dense_lod import dense_lod
from gltf_scene import read_glb, write_glb, accessor, mesh_instances
from cad_glb_composition import RigidComposer
from simplify_package import compact
from plan_cad_lods import digest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

save_mesh = module('equipment', ROOT / 'benchmarks/2026-10-17-equipment-pipeline/run.py').save_mesh
counts = module('budget', ROOT / 'benchmarks/2026-10-17-arena-budget/run.py').counts
TARGETS = {'dart-station/frame': [1,101], 'dart-station/deck-and-shared-hardware': [302,39,51,14], 'dart-station/door-candidate': [4,22,23,24,25,26,27],
           'outpost/fixed/upper-cluster': [1,9,28], 'outpost/fixed/lower-cluster': [1,10,5,6,7,8,9], 'outpost/fixed/column-cluster': [1,2,3],
           'outpost/rotor/module-0': [1,2,3,4,6], 'outpost/rotor/module-1': [1,2,3,4,6], 'outpost/rotor/module-2': [1,2,3,4,6]}


def join(chunks):
    pp=[];tt=[];mm=[];uu=[];offset=0
    for p,t,m,u in chunks:pp.append(p);tt.append(t+offset);mm.append(m);uu.extend([u]*len(t));offset+=len(p)
    return np.concatenate(pp),np.concatenate(tt),np.concatenate(mm),np.array(uu)


def patch_visual(source, replacements, folder, palette):
    """Preserve untouched accessor payloads and every existing PBR material."""
    d,b = read_glb(source); changed = copy.deepcopy(d); selected = {int(u) for *_,u in replacements}
    for node in changed['nodes']:
        if 'mesh' in node and node.get('extras',{}).get('native_shell_index') in selected: del node['mesh']
    used = sorted({n['mesh'] for n in changed['nodes'] if 'mesh' in n}); remap = {old:new for new,old in enumerate(used)}; changed['meshes'] = [changed['meshes'][i] for i in used]
    for node in changed['nodes']:
        if 'mesh' in node: node['mesh'] = remap[node['mesh']]
    p,t,m,u = join(replacements); save_mesh(folder,'replacement',p,t,m,palette,u); rd,rb = read_glb(folder/'replacement.glb')
    for node in rd['nodes']:
        if 'mesh' in node: node['extras'].update(derived_geometry=True,native_identity_claim=False,source_native_shell_index=node['extras'].pop('native_shell_index'))
    # Each new material must reuse an exact source PBR definition, not fallback paint.
    material_map = {}
    for i, mat in enumerate(rd.get('materials',[])):
        color = mat['extras']['step_colour_srgb']; matches = [j for j,v in enumerate(d['materials']) if v.get('extras',{}).get('step_colour_srgb') == color]
        if len(matches) != 1: raise ValueError('source material binding is ambiguous')
        if any('Texture' in k for k in d['materials'][matches[0]].get('pbrMetallicRoughness',{})): raise ValueError('selected textured primitive requires UV-preserving LOD')
        material_map[i] = matches[0]
    composer = RigidComposer(); composer.append_definition('retained',changed,b); mesh_offset = len(composer.document['meshes']); composer.append_definition('detail',rd,rb)
    for mesh in composer.document['meshes'][mesh_offset:]:
        for prim in mesh['primitives']: prim['material'] = material_map[prim['material']-len(d['materials'])]
    composer.document['materials'] = copy.deepcopy(d['materials'])
    composer.document['nodes'].append({'name':'inspection-detail-root','children':[],'extras':{'inspection_only':True}}); root = len(composer.document['nodes'])-1; composer.document['scenes'][0]['nodes']=[root]
    composer.instantiate('retained',root); composer.instantiate('detail',root)
    blob = compact(composer.document,composer.binary); write_glb(folder/'visual.glb',composer.document,blob)
    return counts(folder/'visual.glb')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--only');args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    prior=ROOT/'out/rmuc2027-arena-budget/summary.json'; ledger=json.loads(prior.read_bytes()); by={r['id']:r for r in ledger['components']}; rows=[]
    for cid,selected in TARGETS.items():
        if args.only and cid != args.only:continue
        folder=out/cid;folder.mkdir(parents=True,exist_ok=True);row=by[cid];source=ROOT/row['visual_glb'];data=np.load(source.with_suffix('.npz'));p,t,m,u=[data[k] for k in ['positions_mm','triangles','material_ids','unit_ids']];palette=[v or None for v in data['palette'].tolist()]
        if digest(source)!=row['visual_sha256']:raise ValueError('approved input changed')
        summary_path=folder/'summary.json'
        if summary_path.exists():
            cached=json.loads(summary_path.read_bytes())
            if cached['producer_sha256']!=digest(__file__) or cached['pass_sha256']!=digest(ROOT/'python/cad_dense_lod.py') or cached['source_visual_sha256']!=digest(source):raise ValueError('stale cache')
            for name,sha in cached['outputs_sha256'].items():
                if digest(folder/name)!=sha:raise ValueError('cached output changed')
            rows.append(cached);print('cached',cid,flush=True);continue
        optical=[i for i,c in enumerate(palette) if c and np.ptp(list(map(float,c.split(','))))>.1]
        port_paths=[]
        if cid == 'outpost/fixed/upper-cluster':
            # Native face 72 contains the upper plate's projectile-clear port.
            # Keep a local 20 mm ring around every larger source hole on it.
            # A center ray alone would miss a reduced sphere clearance here.
            from cad_collision_profiles import native_loops
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.TopoDS import TopoDS
            source_step=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step'
            native=module('source',ROOT/'benchmarks/2026-10-17-composed-pipeline/run.py').native
            doc,reader,faces,shells,owner=native(source_step)
            if owner[72]!=1:raise ValueError('upper port source binding changed')
            face=TopoDS.Face(faces.FindKey(72));n=np.array(BRepAdaptor_Surface(face).Plane().Axis().Direction().Coord());loops,_=native_loops(face,close_holes_below_mm=17)
            for loop in loops:
                if not loop['outer']:
                    center=loop['points_mm'].mean(0);port_paths.append((center-n*12,center+n*12))
        visual=[];contact=[];proofs=[]
        for unit in np.unique(u):
            mask=u==unit;used,inv=np.unique(t[mask],return_inverse=True);pp,tt,mm=p[used],inv.reshape(-1,3),m[mask];record={'source_member':int(unit),'input_triangles':len(tt)}
            if int(unit) in selected and len(tt)>=128:
                q,f,k,proof=dense_lod(pp,tt,mm,nominal_error_mm=1,maximum_distance_mm=2,protected_material_ids=optical)
                record['visual']=proof
                if len(f)<len(tt):visual.append((q,f,k,int(unit)))
            zeros=np.zeros(len(tt),np.int64)
            contact_protected=[]
            if unit==1 and port_paths:
                from cad_dense_lod import surface_samples
                samples=surface_samples(pp,tt);keep=np.zeros(len(tt),bool)
                for start,end in port_paths:
                    delta=end-start;fraction=np.clip(((samples-start)@delta)/(delta@delta),0,1)
                    keep|=np.linalg.norm(samples-start-fraction[:,:,None]*delta,axis=2).min(1)<=20
                zeros[keep]=1;contact_protected=[1]
                record['preserved_native_port']={'native_face_index':72,'ring_radius_mm':20,'exact_triangles':int(keep.sum()),'paths_mm':[[s.tolist(),e.tolist()] for s,e in port_paths]}
            if len(tt)>=128:
                q,f,k,proof=dense_lod(pp,tt,zeros,nominal_error_mm=3,maximum_distance_mm=6,protected_material_ids=contact_protected);record['collision']=proof
            else:q,f,k=pp,tt,zeros
            k=np.zeros(len(f),np.int64)
            contact.append((q,f,k,int(unit)));proofs.append(record)
            if int(unit) in selected: print(cid,int(unit),'visual',record.get('visual',{}).get('output_triangles',len(tt)),'collision',len(f),'from',len(tt),flush=True)
        if visual:
            stats=patch_visual(source,visual,folder,palette)
        else:
            d,b=read_glb(source);write_glb(folder/'visual.glb',d,b);stats=counts(folder/'visual.glb')
        q,f,k,owners=join(contact);save_mesh(folder,'contact',q,f,k,['0.45,0.65,0.80'],owners)
        cd,cb=read_glb(folder/'contact.glb')
        for node in cd['nodes']:
            if 'mesh' in node:node['extras'].update(collision_only=True,derived_geometry=True,native_identity_claim=False,source_native_shell_index=node['extras'].pop('native_shell_index'))
        write_glb(folder/'contact.glb',cd,cb)
        accepted=len(f)<row['collision_budget_per_definition']; contact_path=folder/'contact.glb' if accepted else ROOT/row['collision_glb']
        result={'id':cid,'uses':row['uses'],'before':len(t),'visual':stats['placed_triangles'],'collision':len(f) if accepted else row['collision_budget_per_definition'],'previous_collision':row['collision_budget_per_definition'],'contact_adopted':accepted,'contact_glb':str(contact_path.relative_to(ROOT)),'contact_sha256':digest(contact_path),'source_visual_sha256':digest(source),'source_npz_sha256':digest(source.with_suffix('.npz')),'source_step_sha256':digest(ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step'),'members':proofs,'optical_material_ids':optical,'outputs_sha256':{name:digest(folder/name) for name in ['visual.glb','contact.glb','contact.npz']},'producer_sha256':digest(__file__),'pass_sha256':digest(ROOT/'python/cad_dense_lod.py')}
        summary_path.write_text(json.dumps(result,indent=2)+'\n');rows.append(result);print('COMPLETE',cid,'visual',len(t),'->',result['visual'],'collision',result['previous_collision'],'->',result['collision'],flush=True)
    (out/'detail-summary.json').write_text(json.dumps({'components':rows,'prior_ledger_sha256':digest(prior),'producer_sha256':digest(__file__),'scope':'Inspection-only per-rigid-member LOD. Exact optical materials; every triangle/corner sampled per material. No source solid, installed runtime or scoring detector change.'},indent=2)+'\n')


if __name__=='__main__':main()
