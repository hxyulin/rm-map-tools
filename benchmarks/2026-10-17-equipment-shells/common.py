# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-scoped helpers for the aggressive rigid equipment inspection."""
import importlib.util
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,mesh_instances,scene_nodes


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def read_mesh(path):
    d,b=read_glb(path);pp=[];tt=[];mm=[];uu=[];offset=0
    for node,pi,p,t,mi in mesh_instances(d,b):
        e=d['nodes'][node].get('extras',{});u=e.get('source_native_shell_index',e.get('native_shell_index'))
        if u is None:raise ValueError('unbound source member')
        pp.append(p*1000);tt.append(t+offset);mm.extend([mi]*len(t));uu.extend([u]*len(t));offset+=len(p)
    return {'positions_mm':np.concatenate(pp),'triangles':np.concatenate(tt),'material_ids':np.array(mm),'unit_ids':np.array(uu),'palette':[','.join(map(str,v['extras']['step_colour_srgb']))if v['extras']['step_colour_srgb']is not None else None for v in d['materials']]}


def retain_triangles(source,target,selected_indices):
    """Copy surviving source vertex attributes exactly; discard unused payloads."""
    import copy
    from gltf_scene import accessor,write_glb
    from simplify_package import append_accessor,compact
    d,b=read_glb(source);changed=copy.deepcopy(d);binary=bytearray(b);selection=set(map(int,selected_indices));cursor=0;cloned=set()
    for node,pi,p,t,mi in mesh_instances(d,b):
        mesh_index=d['nodes'][node]['mesh']
        keep=np.array([cursor+i in selection for i in range(len(t))]);cursor+=len(t)
        if keep.all():continue
        # Split a shared definition only when this occurrence actually changes.
        if node not in cloned and sum(n.get('mesh')==mesh_index for n in d['nodes'])>1:
            changed['nodes'][node]['mesh']=len(changed['meshes']);changed['meshes'].append(copy.deepcopy(d['meshes'][mesh_index]));cloned.add(node)
        prim=changed['meshes'][changed['nodes'][node]['mesh']]['primitives'][pi]
        if not keep.any():prim['drop']=True;continue
        original_primitive=d['meshes'][mesh_index]['primitives'][pi]
        raw_triangles=accessor(d,b,original_primitive['indices']).reshape(-1,3)
        used,inv=np.unique(raw_triangles[keep],return_inverse=True)
        for key,index in list(prim['attributes'].items()):
            old=d['accessors'][index];values=accessor(d,b,index)[used];new=append_accessor(changed,binary,values,old['type'],old['componentType']);prim['attributes'][key]=new
            if old.get('normalized'):changed['accessors'][new]['normalized']=True
        prim['indices']=append_accessor(changed,binary,inv.reshape(-1).astype(np.uint32),'SCALAR',5125)
        prim.get('extras',{}).pop('source_native_face_runs',None)
        extra=changed['nodes'][node].setdefault('extras',{});owner=extra.pop('native_shell_index',extra.get('source_native_shell_index'));extra.update(source_native_shell_index=owner,derived_geometry=True,native_identity_claim=False,inspection_only=True)
    if selection and max(selection)>=cursor:raise ValueError('unknown input triangle selection')
    for node in changed['nodes']:
        if 'mesh'not in node:continue
        mesh=changed['meshes'][node['mesh']];mesh['primitives']=[p for p in mesh['primitives']if not p.pop('drop',False)]
        if not mesh['primitives']:del node['mesh']
    payload=compact(changed,binary);write_glb(target,changed,payload)


def replace_members(source,target,parts,palette,folder):
    """Keep source traversal order, PBR tables and untouched vertex attributes."""
    import copy
    from cad_glb_composition import RigidComposer
    from gltf_scene import write_glb
    from simplify_package import compact
    save=module('equipment_writer',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py').save_mesh
    d,b=read_glb(source);changed=copy.deepcopy(d);selected={int(u)for p,t,m,u in parts};slots={}
    worlds={i:world for i,world,_ in scene_nodes(d)}
    for index,node in enumerate(changed['nodes']):
        e=node.get('extras',{});u=e.get('source_native_shell_index',e.get('native_shell_index'))
        if 'mesh'in node and u in selected:
            if u in slots or not np.allclose(worlds[index],np.eye(4),atol=1e-12,rtol=0):raise ValueError('replacement requires one baked source node per member')
            slots[u]=index;del node['mesh']
    if set(slots)!=selected:raise ValueError('replacement owner missing from source')
    pp=[];tt=[];mm=[];uu=[];offset=0
    for p,t,m,u in parts:pp.append(p);tt.append(t+offset);mm.append(m);uu.extend([u]*len(t));offset+=len(p)
    save(folder,'replacement',np.concatenate(pp),np.concatenate(tt),np.concatenate(mm),palette,np.array(uu));rd,rb=read_glb(folder/'replacement.glb');material_map={}
    for i,mat in enumerate(rd['materials']):
        color=mat['extras']['step_colour_srgb'];matches=[j for j,v in enumerate(d['materials'])if v['extras']['step_colour_srgb']==color]
        if len(matches)!=1:raise ValueError('ambiguous source material')
        material_map[i]=matches[0]
    for node in rd['nodes']:
        if 'mesh'in node:node['extras'].update(source_native_shell_index=node['extras'].pop('native_shell_index'),derived_geometry=True,native_identity_claim=False)
    composer=RigidComposer();composer.append_definition('retained',changed,b);offset=len(composer.document['meshes']);composer.append_definition('shells',rd,rb)
    for mesh in composer.document['meshes'][offset:]:
        for prim in mesh['primitives']:prim['material']=material_map[prim['material']-len(d['materials'])]
    composer.document['materials']=copy.deepcopy(d['materials']);composer.document['nodes'].append({'name':'equipment-shell-inspection','children':[],'extras':{'inspection_only':True}});composer.document['scenes'][0]['nodes']=[0];composer.instantiate('retained',0)
    for node in rd['nodes']:
        if 'mesh'not in node:continue
        u=node['extras']['source_native_shell_index'];destination=composer.document['nodes'][1+slots[u]];destination['mesh']=offset+node['mesh'];destination['extras'].pop('native_shell_index',None);destination['extras'].update(source_native_shell_index=u,derived_geometry=True,native_identity_claim=False)
    payload=compact(composer.document,composer.binary);write_glb(target,composer.document,payload)
