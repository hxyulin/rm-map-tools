#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Independent native Base detail candidates and a combined inspection export."""
import argparse,json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from validate_parts import read_part
from cad_wall_fill import shape_map
from cad_detail_passes import compound,enclosed,fill_enclosed_voids,small_bore_groups,smooth_bores,mesh_native_detail,sampled_support_error,plug_bores
from export_field_package import GlbWriter
from plan_cad_lods import digest
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID,TopAbs_SHELL,TopAbs_VERTEX,TopAbs_OUT
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--bores',action='store_true');a=parser.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    r=json.loads((a.source/'audit.json').read_bytes());policy_path=ROOT/'rules/base-details-rmuc2027.json';policy=json.loads(policy_path.read_bytes())
    if r['component_step_sha256']!=policy['component_step_sha256']:raise ValueError('unreviewed Base component')
    for name in ('source.step','geometry.npz'):
        if digest(a.source/name)!=r['outputs_sha256'][name]:raise ValueError('source audit payload changed')
    a.out.mkdir(parents=True);data=np.load(a.source/'geometry.npz',allow_pickle=False);source_p=data['positions_mm'];source_t=data['triangles'];source_u=data['unit_ids'];source_f=data['source_face_ids'];source_ci=data['colour_indices'];source_rgb=data['source_srgb'];units=r['units'];unit_index={u['source_id']:i for i,u in enumerate(units)}
    native,reader,error=read_part(str(a.source/'source.step'))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(native.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE)
    if faces.Extent()!=r['source_faces']:raise ValueError('native face inventory changed')
    colour_by_index={f['native_face_index']:f['source_colour'] for f in r['faces']};source_face_by_index={f['native_face_index']:f['source_face_id'] for f in r['faces']};index_by_source={v:k for k,v in source_face_by_index.items()}
    shape_lookup={}
    for kind in (TopAbs_SOLID,TopAbs_SHELL):
        shapes=shape_map(root,kind)
        for j in range(1,shapes.Extent()+1):
            s=shapes.FindKey(j);f=shape_map(s,TopAbs_FACE);key=frozenset(faces.FindIndex(f.FindKey(k)) for k in range(1,f.Extent()+1));shape_lookup[(kind,key)]=s
    unit_shapes={};colours={};native_sources={};baseline={}
    for i,u in enumerate(units):
        key=frozenset(index_by_source[f] for f in u['face_ids']);shape=shape_lookup[(TopAbs_SOLID if u['kind']=='solid' else TopAbs_SHELL,key)];unit_shapes[u['source_id']]=shape;local=shape_map(shape,TopAbs_FACE)
        colours[u['source_id']]=tuple(colour_by_index[faces.FindIndex(local.FindKey(j))] for j in range(1,local.Extent()+1));native_sources[u['source_id']]=[source_face_by_index[faces.FindIndex(local.FindKey(j))] for j in range(1,local.Extent()+1)]
        mask=source_u==i;old_t=source_t[mask];unique,inverse=np.unique(old_t,return_inverse=True)
        # The source diffuse list follows first-seen material insertion order.
        palette=list(r['triangles_by_diffuse']);keys=np.array([None if k=='None' else k for k in palette],dtype=object)
        baseline[u['source_id']]=(source_p[unique],inverse.reshape(-1,3),keys[source_ci[mask]],source_f[mask])
    report={'source_sha256':r['source_sha256'],'component_step_sha256':r['component_step_sha256'],'source_audit_sha256':digest(a.source/'audit.json'),'policy_sha256':digest(policy_path),'baseline_triangles':r['definition_triangles'],'placed_uses':r['placed_uses'],'stages':{},'decisions':{},'scope':'Derived source-pose candidates only; original CAD, runtime and existing bindings unchanged. Whole independently moving units need ownership review before installation.'}
    # Native color lookup is checked against the recorded source RGB, not guessed.
    for source,(p,t,k,f) in baseline.items():
        mask=source_u==unit_index[source];rgb=np.array([[float(v) for v in c.split(',')] if c else [.6275]*3 for c in k])
        if not np.allclose(rgb,source_rgb[source_ci[mask]],rtol=0,atol=1e-8):raise ValueError('source palette order changed')
    def save_report():
        report['producer_sha256']={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_detail_passes.py']}
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def write_stage(name,replacements=None,removed=None):
        replacements=replacements or {};removed=removed or set();writer=GlbWriter('base/'+name,{'version':'2.0','copyright':'DJI / RoboMaster source geometry; derived detail-pass candidate'})
        points=[];triangles=[];ids=[];rgb=[];faceids=[];offset=0;per_unit={};unchanged=0
        for i,u in enumerate(units):
            source=u['source_id']
            if source in removed:continue
            p,t,keys,f=replacements.get(source,baseline[source]);writer.add_node('source-unit-'+str(source),p/1000,t,list(keys),extras={'source_unit_id':source,'inspection_only':True,'derived':source in replacements});per_unit[str(source)]=len(t)
            if source not in replacements:unchanged+=1
            points.append(p);triangles.append(t+offset);offset+=len(p);ids.extend([i]*len(t));faceids.append(f);rgb.append(np.array([[float(v) for v in c.split(',')] if c else [.6275]*3 for c in keys]))
        folder=a.out/name;folder.mkdir();writer.write(folder/'visual.glb');np.savez(folder/'geometry.npz',positions_mm=np.concatenate(points),triangles=np.concatenate(triangles),unit_ids=np.array(ids,dtype=np.uint32),source_face_ids=np.concatenate(faceids),triangle_srgb=np.concatenate(rgb))
        total=sum(per_unit.values());report['stages'][name]={'definition_triangles':total,'placed_triangles':total*r['placed_uses'],'per_unit_triangles':per_unit,'removed_source_units':sorted(removed),'changed_source_units':sorted(replacements),'byte_exact_retained_original_units':unchanged,'visual_sha256':digest(folder/'visual.glb'),'geometry_sha256':digest(folder/'geometry.npz')};save_report();print(name,total,'triangles',flush=True)
    write_stage('baseline')
    # A: remove only closed source cavity boundaries, retaining original meshes.
    void_replacements={};void_native={};void_decisions=[]
    for u in units:
        source=u['source_id']
        if u['kind']!='solid' or shape_map(unit_shapes[source],TopAbs_SHELL).Extent()<2:continue
        try:
            result=fill_enclosed_voids(unit_shapes[source],colours[source]);kept={native_sources[source][i[0]-1] for i in result.source_face_indices};p,t,k,f=baseline[source];mask=np.isin(f,list(kept));void_replacements[source]=(p,t[mask],k[mask],f[mask]);void_native[source]=result;void_decisions.append({'source_unit':source,'accepted':True,'proof':result.proof})
        except ValueError as e:void_decisions.append({'source_unit':source,'accepted':False,'reason':str(e)})
    report['decisions']['enclosed_voids']=void_decisions;write_stage('enclosed-voids',void_replacements)
    # B: test full native surfaces of small non-light units against valid material.
    opaque={source:(void_native[source].shape if source in void_native else unit_shapes[source]) for source in unit_shapes if units[unit_index[source]]['kind']=='solid'};opaque={s:v for s,v in opaque.items() if BRepCheck_Analyzer(v).IsValid()}
    removed=set();hidden=[];bounds={u['source_id']:np.array(u['bbox_mm']) for u in units}
    for u in units:
        source=u['source_id'];span=np.ptp(bounds[source],axis=0)
        if span.max()>policy['hidden_unit_maximum_span_mm'] or any(f['source_colour'] in ('1.0000,0.0000,0.0000','0.0650,0.9810,0.0620') for f in r['faces'] if f['unit']==unit_index[source]):continue
        for outer,shape in opaque.items():
            if outer==source or np.any(bounds[source][0]<=bounds[outer][0]+.001) or np.any(bounds[source][1]>=bounds[outer][1]-.001):continue
            # Vertex tests only reject cheaply; they never authorize removal.
            verts=shape_map(unit_shapes[source],TopAbs_VERTEX);outside=False
            for j in range(1,verts.Extent()+1):
                point=BRep_Tool.Pnt_s(TopoDS.Vertex(verts.FindKey(j)))
                if BRepClass3d_SolidClassifier(shape,point,1e-7).State()==TopAbs_OUT:outside=True;break
            if outside:continue
            evidence=enclosed(unit_shapes[source],shape,clearance_mm=policy['enclosure_clearance_mm'])
            if evidence['accepted']:removed.add(source);hidden.append({'source_unit':source,'opaque_source_unit':outer,'proof':evidence});print('Enclosed small unit',source,'in',outer,flush=True);break
    report['decisions']['hidden_units']=hidden;write_stage('hidden-units',void_replacements,removed)
    # C: independent whole-unit source tessellation, keeping all other units exact.
    targets=policy['native_lod_source_units'];lod_replacements={};lod_decisions=[]
    def remesh(source,shape,keys,original_ids,*,linear=.1,angular=.6):
        p,t,k,f,proof=mesh_native_detail(shape,keys,linear_deflection_mm=linear,angular_deflection_rad=angular)
        proof['support_check']=sampled_support_error(shape,p,t,f,limit_mm=max(policy['sampled_support_limit_mm'],linear*1.2))
        return (p,t,np.array(k,dtype=object),np.array([original_ids[i-1] for i in f],dtype=np.uint32)),proof
    for source in targets:
        try:
            mesh,proof=remesh(source,unit_shapes[source],colours[source],native_sources[source]);lod_replacements[source]=mesh;lod_decisions.append({'source_unit':source,'accepted':True,'proof':proof})
        except ValueError as e:lod_decisions.append({'source_unit':source,'accepted':False,'reason':str(e)})
    report['decisions']['native_detail_lod']=lod_decisions;write_stage('native-detail-lod',lod_replacements)
    # D: independently reduce tiny analytic hardware while protecting lights.
    hardware_replacements={};hardware_decisions=[]
    for u in units:
        source=u['source_id'];span=np.ptp(bounds[source],axis=0);records=[f for f in r['faces'] if f['unit']==unit_index[source]]
        if span.max()>policy['small_hardware_maximum_span_mm'] or any(f['surface'] not in policy['small_hardware_allowed_surfaces'] or f['source_colour'] in ('1.0000,0.0000,0.0000','0.0650,0.9810,0.0620') for f in records):continue
        try:
            mesh,proof=remesh(source,unit_shapes[source],colours[source],native_sources[source]);hardware_replacements[source]=mesh;hardware_decisions.append({'source_unit':source,'accepted':True,'proof':proof})
        except ValueError as e:hardware_decisions.append({'source_unit':source,'accepted':False,'reason':str(e)})
    report['decisions']['small_hardware_lod']=hardware_decisions;write_stage('small-hardware-lod',hardware_replacements)
    # E: a separately bounded smoothing trial; the source crossbar is invalid.
    bore_replacements={};bore_native={};bore_decisions=[]
    if a.bores:
        source=policy['bore_source_units'][0];groups=small_bore_groups(unit_shapes[source],maximum_radius_mm=policy['bore_maximum_radius_mm'],maximum_depth_mm=policy['bore_maximum_depth_mm'])
        selected=groups;print('Smoothing',len(selected),'of',len(groups),'complete bores',flush=True)
        try:
            result=plug_bores(unit_shapes[source],colours[source],selected,maximum_added_volume_mm3=policy['maximum_added_bore_volume_mm3'],radial_overlap_mm=policy['bore_radial_overlap_mm']);original_ids=[native_sources[source][ids[0]-1] if len(ids)==1 else 0 for ids in result.source_face_indices]
            mesh,proof=remesh(source,result.shape,result.face_colours,original_ids,linear=.4,angular=.25);bore_replacements[source]=mesh;bore_native[source]=result;bore_decisions.append({'source_unit':source,'accepted':True,'groups':selected,'proof':result.proof,'mesh':proof})
        except ValueError as e:bore_decisions.append({'source_unit':source,'accepted':False,'reason':str(e),'candidate_groups':len(groups)})
    report['decisions']['smooth_bores']=bore_decisions;write_stage('smooth-bores',bore_replacements)
    combined={**void_replacements,**lod_replacements,**hardware_replacements}
    for source,result in bore_native.items():
        original_ids=[native_sources[source][ids[0]-1] if len(ids)==1 else 0 for ids in result.source_face_indices]
        mesh,proof=remesh(source,result.shape,result.face_colours,original_ids);combined[source]=mesh
        report['decisions']['smooth_bores'][0]['combined_lod_mesh']=proof
    write_stage('combined',combined,removed);save_report()
if __name__=='__main__':main()
