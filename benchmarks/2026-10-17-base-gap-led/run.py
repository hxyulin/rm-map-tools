#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Width-aware Base collision closure and stricter LED material LOD trials."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_surface_lods import material_lod,profile_prism,close_bore_surfaces
from cad_detail_passes import mesh_native_detail
from cad_wall_fill import shape_map
from mesh_quality import deviation
from export_field_package import GlbWriter
from plan_cad_lods import digest
from validate_parts import read_part
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID,TopAbs_SHELL
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def main():
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument('--source',type=Path,required=True);arg.add_argument('--reference',type=Path,required=True);arg.add_argument('--out',type=Path,required=True);a=arg.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    policy_path=ROOT/'rules/base-gap-led-rmuc2027.json';policy=json.loads(policy_path.read_bytes());audit=json.loads((a.source/'audit.json').read_bytes());reference=json.loads((a.reference/'summary.json').read_bytes())
    if digest(a.source/'source.step')!=policy['component_step_sha256']:raise ValueError('source mismatch')
    data={}
    for stage in ('approved','visual-lod','collision'):
        if digest(a.reference/stage/'geometry.npz')!=reference['stages'][stage]['geometry_sha256']:raise ValueError('reference hash mismatch')
        d=np.load(a.reference/stage/'geometry.npz');data[stage]={k:d[k] for k in d.files}
    a.out.mkdir(parents=True);base=data['approved'];palette,mat=np.unique(base['triangle_srgb'],axis=0,return_inverse=True);led={i for i,c in enumerate(palette) if ','.join(f'{v:.4f}' for v in c) in policy['led_rgb']};units=audit['units'];report={'component_step_sha256':policy['component_step_sha256'],'policy_sha256':digest(policy_path),'reference_summary_sha256':digest(a.reference/'summary.json'),'material_palette_srgb':palette.tolist(),'led_material_ids':sorted(led),'reference_counts':{s:reference['stages'][s]['definition_triangles'] for s in reference['stages']},'visual_decisions':[],'collision_decisions':[],'stages':{},'scope':policy['scope']}
    def unpack(d,index):
        mask=d['unit_ids']==index;t=d['triangles'][mask];used,inv=np.unique(t,return_inverse=True);return d['positions_mm'][used],inv.reshape(-1,3),d['triangle_srgb'][mask],d['source_face_ids'][mask]
    def save():
        report['producer_sha256']={str(p.relative_to(ROOT)):digest(p) for p in (Path(__file__),ROOT/'python/cad_surface_lods.py',ROOT/'python/simplify_package.py',ROOT/'python/mesh_quality.py')};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def write(stage,parts):
        folder=a.out/stage;folder.mkdir();writer=GlbWriter('base/'+stage,{'version':'2.0','copyright':'DJI / RoboMaster geometry; derived gap/LED LOD inspection candidate'});pp=[];tt=[];cc=[];ff=[];uu=[];offset=0;counts={};led_count=0
        for i,u in enumerate(units):
            source=u['source_id']
            if source not in parts:continue
            p,t,c,f=parts[source];writer.add_node('source-unit-'+str(source),p/1000,t,[','.join(f'{v:.4f}' for v in col) for col in c],extras={'source_unit_id':source,'inspection_only':True,'role':'collision-only' if stage=='collision' else 'visual'});pp.append(p);tt.append(t+offset);offset+=len(p);cc.append(c);ff.append(f);uu.extend([i]*len(t));counts[str(source)]=len(t);led_count+=int((((c[:,0]>.9)&(c[:,1]<.1))|((c[:,1]>.9)&(c[:,0]<.1))).sum())
        writer.write(folder/'visual.glb');np.savez(folder/'geometry.npz',positions_mm=np.concatenate(pp),triangles=np.concatenate(tt),triangle_srgb=np.concatenate(cc),source_face_ids=np.concatenate(ff),unit_ids=np.asarray(uu,dtype=np.uint32));report['stages'][stage]={'definition_triangles':sum(counts.values()),'placed_triangles':2*sum(counts.values()),'per_unit_triangles':counts,**({'led_triangles':led_count} if stage=='visual' else {}),'visual_sha256':digest(folder/'visual.glb'),'geometry_sha256':digest(folder/'geometry.npz')};save();print(stage,sum(counts.values()),'triangles; lights',led_count,flush=True)
    visual={};overrides={i:{'error_mm':policy['led_error_mm'],'sampled_limit_mm':policy['led_sampled_limit_mm']} for i in led}
    for i,u in enumerate(units):
        source=u['source_id'];p,t,c,f=unpack(base,i);m=mat[base['unit_ids']==i]
        try:
            p1,t1,m1,proof=material_lod(p,t,m,error_mm=policy['visual_error_mm'],sampled_limit_mm=policy['visual_sampled_limit_mm'],material_policies=overrides,sample_count=4096)
            previous=unpack(data['visual-lod'],i)
            if len(t1)>len(previous[1]):
                visual[source]=previous;decision={'source_unit_id':source,'operation':'retain-approved-lod','reason':'candidate is larger than the approved unit','trial_proof':proof}
            else:visual[source]=(p1,t1,palette[m1],np.zeros(len(t1),dtype=np.uint32));decision={'source_unit_id':source,'operation':'material-lod','proof':proof}
        except ValueError as e:visual[source]=unpack(data['visual-lod'],i);decision={'source_unit_id':source,'operation':'retain-approved-lod','reason':str(e)}
        report['visual_decisions'].append(decision)
    write('visual',visual)
    native,_,error=read_part(str(a.source/'source.step'))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(native.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);by_id={f['source_face_id']:f['native_face_index'] for f in audit['faces']};lookup={}
    for kind in (TopAbs_SOLID,TopAbs_SHELL):
        shapes=shape_map(root,kind)
        for j in range(1,shapes.Extent()+1):
            shape=shapes.FindKey(j);local=shape_map(shape,TopAbs_FACE);lookup[(kind,frozenset(faces.FindIndex(local.FindKey(k)) for k in range(1,local.Extent()+1)))]=shape
    collision={u['source_id']:unpack(data['collision'],i) for i,u in enumerate(units) if np.any(data['collision']['unit_ids']==i)};profile_faces=dict(policy['collision_backing_source_faces'])
    for source in policy['collision_bore_source_units']+list(profile_faces):
        i=next(i for i,u in enumerate(units) if u['source_id']==source);u=units[i];original=collision[source];face_list=[by_id[f] for f in u['face_ids']]
        shape=lookup[(TopAbs_SOLID if u['kind']=='solid' else TopAbs_SHELL,frozenset(face_list))]
        try:
            if source in profile_faces:
                derived,proof=profile_prism(faces.FindKey(by_id[profile_faces[source]]),depth_mm=1.5,maximum_gap_mm=policy['strict_collision_gap_mm'])
            else:
                derived,native_ids,proof=close_bore_surfaces(shape,maximum_gap_mm=policy['strict_collision_gap_mm'])
                local_faces=shape_map(shape,TopAbs_FACE);source_by_index={record['native_face_index']:record['source_face_id'] for record in audit['faces']};proof['source_face_ids_by_local_index']=[source_by_index[faces.FindIndex(local_faces.FindKey(k))] for k in range(1,local_faces.Extent()+1)]
            n=shape_map(derived,TopAbs_FACE).Extent();p,t,_,_,meshproof=mesh_native_detail(derived,[None]*n,linear_deflection_mm=.25,angular_deflection_rad=.8)
            p,t,_,lod=material_lod(p,t,np.zeros(len(t),dtype=np.int32),error_mm=policy['collision_mesh_error_mm'],sampled_limit_mm=policy['collision_mesh_sampled_limit_mm'],sample_count=4096)
            measured=deviation(original[0],original[1],p,t,count=4096)
            if measured['max']>policy['collision_reference_sampled_limit_mm']:raise ValueError('collision reference deviation exceeds 15 mm')
            if len(t)>=len(original[1]):
                report['collision_decisions'].append({'source_unit_id':source,'accepted':False,'reason':'collision replacement does not save triangles','proof':proof,'lod':lod,'reference_deviation_mm':measured,'before_triangles':len(original[1]),'after_triangles':len(t)});print('collision retained',source,'no triangle saving',flush=True);continue
            collision[source]=(p,t,np.tile([.2,.65,.75],(len(t),1)),np.zeros(len(t),dtype=np.uint32));decision={'source_unit_id':source,'accepted':True,'proof':proof,'mesh':meshproof,'lod':lod,'reference_deviation_mm':measured,'before_triangles':len(original[1]),'after_triangles':len(t)}
            print('collision accepted',source,len(original[1]),'->',len(t),flush=True)
        except ValueError as e:decision={'source_unit_id':source,'accepted':False,'reason':str(e)};print('collision retained',source,str(e),flush=True)
        report['collision_decisions'].append(decision);save()
    write('collision',collision);save()


if __name__=='__main__':main()
