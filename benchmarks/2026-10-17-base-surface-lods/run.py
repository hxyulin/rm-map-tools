#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare appearance-protected Base visuals and independently coarse collision."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_surface_lods import material_lod,profile_prism
from mesh_quality import deviation
from cad_detail_passes import compound,mesh_native_detail
from cad_wall_fill import shape_map
from plan_cad_lods import digest
from export_field_package import GlbWriter
from validate_parts import read_part
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.TopAbs import TopAbs_FACE


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--approved',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    policy_path=ROOT/'rules/base-surface-lods-rmuc2027.json';policy=json.loads(policy_path.read_bytes());audit=json.loads((a.source/'audit.json').read_bytes());approved=json.loads((a.approved/'summary.json').read_bytes())
    if audit['component_step_sha256']!=policy['component_step_sha256'] or digest(a.source/'source.step')!=policy['component_step_sha256']:raise ValueError('source mismatch')
    if digest(a.approved/'combined/geometry.npz')!=approved['stages']['combined']['geometry_sha256']:raise ValueError('approved geometry changed')
    a.out.mkdir(parents=True);d=np.load(a.approved/'combined/geometry.npz');points=d['positions_mm'];triangles=d['triangles'];uids=d['unit_ids'];rgb=d['triangle_srgb'];faceids=d['source_face_ids'];units=audit['units'];palette,material=np.unique(rgb,axis=0,return_inverse=True)
    protected={i for i,c in enumerate(palette) if ','.join(f'{v:.4f}' for v in c) in policy['visual_protected_source_rgb']}
    report={'component_step_sha256':policy['component_step_sha256'],'source_audit_sha256':digest(a.source/'audit.json'),'approved_summary_sha256':digest(a.approved/'summary.json'),'policy_sha256':digest(policy_path),'placed_uses':audit['placed_uses'],'stages':{},'visual_decisions':[],'collision_decisions':[],'protected_material_ids':sorted(protected),'scope':'Source-pose review candidates; separate collider skin only, no gameplay detectors, motion ownership, original STEP or runtime changes.'}
    base={}
    for i,u in enumerate(units):
        mask=uids==i;t=triangles[mask];used,inverse=np.unique(t,return_inverse=True);base[u['source_id']]=(points[used],inverse.reshape(-1,3),material[mask],faceids[mask])
    def save():
        report['producer_sha256']={str(x.relative_to(ROOT)):digest(x) for x in [Path(__file__),ROOT/'python/cad_surface_lods.py']};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def write(name,replacements,removed=()):
        path=a.out/name;path.mkdir();writer=GlbWriter('base/'+name,{'version':'2.0','copyright':'DJI / RoboMaster source geometry; derived Base LOD inspection candidate'});pp=[];tt=[];mm=[];ff=[];uu=[];offset=0;counts={};protected_count=0
        for i,u in enumerate(units):
            source=u['source_id']
            if source in removed:continue
            p,t,m,f=replacements.get(source,base[source]);keys=[','.join(f'{v:.4f}' for v in c) for c in palette[m]]
            writer.add_node('source-unit-'+str(source),p/1000,t,keys,extras={'source_unit_id':source,'inspection_only':True,'role':'collision-only' if name=='collision' else 'visual','derived':source in replacements});pp.append(p);tt.append(t+offset);offset+=len(p);mm.append(palette[m]);ff.append(f);uu.extend([i]*len(t));counts[str(source)]=len(t)
            old=base[source];keep=np.isin(old[2],list(protected))
            if name!='collision':
                new=np.isin(m,list(protected))
                if not np.array_equal(p[t[new]],old[0][old[1][keep]]) or not np.array_equal(m[new],old[2][keep]):raise ValueError('protected light triangles changed')
                protected_count+=int(new.sum())
            if source not in replacements:
                if not np.array_equal(p[t],old[0][old[1]]) or not np.array_equal(m,old[2]) or not np.array_equal(f,old[3]):raise ValueError('unselected unit changed')
        writer.write(path/'visual.glb');np.savez(path/'geometry.npz',positions_mm=np.concatenate(pp),triangles=np.concatenate(tt),triangle_srgb=np.concatenate(mm),source_face_ids=np.concatenate(ff),unit_ids=np.asarray(uu,dtype=np.uint32))
        count=sum(counts.values());report['stages'][name]={'definition_triangles':count,'placed_triangles':count*audit['placed_uses'],'per_unit_triangles':counts,'changed_source_units':sorted(replacements),'removed_source_units':sorted(removed),'protected_light_triangles_checked':protected_count,'unchanged_units_checked':len(counts)-len(replacements),'visual_sha256':digest(path/'visual.glb'),'geometry_sha256':digest(path/'geometry.npz')};save();print(name,count,flush=True)
    write('approved',{})
    visual={}
    for source in policy['visual_source_units']:
        old=base[source]
        try:
            p,t,m,proof=material_lod(old[0],old[1],old[2],error_mm=policy['visual_error_mm'],sampled_limit_mm=policy['visual_sampled_limit_mm'],protected_material_ids=protected)
            # Region-level lineage is recorded below. New finite triangles do not
            # pretend to own one original CAD face; untouched lights keep theirs.
            f=np.zeros(len(t),dtype=np.uint32)
            for col in protected:f[m==col]=old[3][old[2]==col]
            visual[source]=(p,t,m,f);decision={'source_unit_id':source,'accepted':True,'source_face_ids':units[next(i for i,u in enumerate(units) if u['source_id']==source)]['face_ids'],'proof':proof}
        except ValueError as e:decision={'source_unit_id':source,'accepted':False,'reason':str(e)}
        report['visual_decisions'].append(decision);print('visual',source,decision['accepted'],len(visual[source][1]) if source in visual else decision['reason'],flush=True)
    write('visual-lod',visual)
    native,_,error=read_part(str(a.source/'source.step'))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(native.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);by_id={f['source_face_id']:f['native_face_index'] for f in audit['faces']};profiles={};profile_proofs={}
    for spec in policy['collision_profiles']:
        source=spec['source_unit_id'];print('profile',source,spec['source_face_id'],flush=True);shape,proof=profile_prism(faces.FindKey(by_id[spec['source_face_id']]),depth_mm=spec['signed_depth_mm'],maximum_filled_hole_area_mm2=spec['maximum_filled_hole_area_mm2']);profiles.setdefault(source,[]).append(shape);profile_proofs.setdefault(source,[]).append({'source_face_id':spec['source_face_id'],'proof':proof})
    collision={};removed=[]
    for i,u in enumerate(units):
        source=u['source_id'];p,t,m,f=base[source]
        if source in profiles:
            shape=compound(profiles[source]);n=shape_map(shape,TopAbs_FACE).Extent();p,t,_,_,proof=mesh_native_detail(shape,[None]*n,linear_deflection_mm=.5,angular_deflection_rad=1.)
            old=base[source];sampled=deviation(old[0],old[1],p,t,count=4096)
            if sampled['max']<=policy['collision_profile_sampled_limit_mm']:
                collision[source]=(p,t,np.zeros(len(t),dtype=material.dtype),np.zeros(len(t),dtype=np.uint32));report['collision_decisions'].append({'source_unit_id':source,'operation':'source-profile-replacement','profiles':profile_proofs[source],'mesh':proof,'sampled_deviation_mm':sampled});continue
            report['collision_decisions'].append({'source_unit_id':source,'operation':'reject-profile-replacement','profiles':profile_proofs[source],'sampled_deviation_mm':sampled,'reason':'source-profile plate omits a substantial source projection; use coarse source mesh instead'})
            p,t,m,f=old
        if max(np.ptp(np.asarray(u['bbox_mm']),axis=0))<=policy['collision_omit_maximum_span_mm'] and not np.isin(m,list(protected)).any():
            removed.append(source);report['collision_decisions'].append({'source_unit_id':source,'operation':'omit-small-hardware-collider','maximum_span_mm':float(max(np.ptp(np.asarray(u['bbox_mm']),axis=0)))})
        else:
            try:
                p,t,mm,proof=material_lod(p,t,np.zeros(len(t),dtype=material.dtype),error_mm=policy['collision_error_mm'],sampled_limit_mm=policy['collision_sampled_limit_mm']);collision[source]=(p,t,mm,np.zeros(len(t),dtype=np.uint32));report['collision_decisions'].append({'source_unit_id':source,'operation':'coarse-mesh','proof':proof})
            except ValueError as e:report['collision_decisions'].append({'source_unit_id':source,'operation':'retain-approved','reason':str(e)})
    write('collision',collision,removed);save()


if __name__=='__main__':main()
