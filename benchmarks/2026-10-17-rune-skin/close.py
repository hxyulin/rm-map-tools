#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Close simplified Rune arms with one flat native-profile rear panel each."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from run import module
from cad_flat_back import flat_back
from cad_detail_passes import area,mesh_native_detail
from cad_wall_fill import shape_map
from cad_planar_shell import planar_skin
from plan_cad_lods import digest
from validate_parts import read_part
from export_field_package import GlbWriter
from OCP.TopAbs import TopAbs_SHELL,TopAbs_FACE,TopAbs_REVERSED
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--id');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    skins=ROOT/'out/rmuc2027-rune-skin';skin_report=json.loads((skins/'summary.json').read_bytes());prior=ROOT/'out/rmuc2027-rune-detail';source=ROOT/'out/rmuc2027-equipment-pipeline';pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');results=[]
    for original in skin_report['components']:
        cid=original['id']
        if a.id and cid!=a.id:continue
        target=a.out/cid;target.mkdir(parents=True,exist_ok=True);path=prior/cid/'candidate.npz';base=np.load(path);arm='/arm-' in cid;pp=[];tt=[];mm=[];uu=[];offset=0;cap_proof=None;removed_hardware=[];cap_count=0
        if arm:
            if digest(skins/cid/'candidate.npz')!=original['outputs_sha256']['candidate.npz']:raise ValueError('skin input changed')
            d=np.load(skins/cid/'candidate.npz');keep=np.ones(len(d['triangles']),bool);front=np.array(original['selection']['front_direction']);palette=[v or None for v in d['palette'].tolist()]
            # Tiny neutral shells are deliberately omitted, not labeled proven hidden.
            for unit in np.unique(d['unit_ids']):
                ids=base['unit_ids']==unit;p=base['positions_mm'][base['triangles'][ids]].reshape(-1,3);materials=np.unique(base['material_ids'][ids]);chromatic=any(palette[k] is not None and np.ptp(list(map(float,palette[k].split(','))))>.1 for k in materials)
                if np.ptp(p,axis=0).max()<=17 and not chromatic:keep[d['unit_ids']==unit]=False;removed_hardware.append(int(unit))
            pp.append(d['positions_mm']);tt.append(d['triangles'][keep]);mm.append(d['material_ids'][keep]);uu.append(d['unit_ids'][keep]);offset=len(d['positions_mm'])
            step=source/cid/'source.step'
            if digest(step)!=original['original_source_step_sha256']:raise ValueError('native source changed')
            doc,reader,error=read_part(str(step))
            if error:raise ValueError(error)
            labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels);root=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));shells=shape_map(root,TopAbs_SHELL);profiles=[];bindings=[]
            for unit in [11,7]:
                faces=shape_map(shells.FindKey(unit),TopAbs_FACE);candidates=[]
                for i in range(1,faces.Extent()+1):
                    face=TopoDS.Face(faces.FindKey(i));surface=BRepAdaptor_Surface(face)
                    if surface.GetType()!=GeomAbs_Plane:continue
                    direction=surface.Plane().Axis().Direction();n=np.array([direction.X(),direction.Y(),direction.Z()])*(-1 if face.Orientation()==TopAbs_REVERSED else 1)
                    if n@front<-.999999:candidates.append((area(face),i,face))
                if not candidates:raise ValueError('missing reviewed rear housing profile')
                size,index,face=max(candidates,key=lambda x:x[0]);profiles.append(face);bindings.append({'native_shell_index':unit,'shell_local_face_index':index,'source_area_mm2':size})
            plane=BRepAdaptor_Surface(profiles[0]).Plane();point=plane.Location();rear=float(np.array([point.X(),point.Y(),point.Z()])@front);cap,cap_proof=flat_back(profiles,front,rear,maximum_gap_mm=17);cap_proof['source_profiles']=bindings
            nfaces=shape_map(cap,TopAbs_FACE).Extent();cp,ct,_,_,meshing=mesh_native_detail(cap,['0.2000,0.2000,0.2000']*nfaces,linear_deflection_mm=.25,angular_deflection_rad=.4);dark=palette.index('0.2000,0.2000,0.2000');cp,ct,cm,skin=planar_skin(cp,ct,np.full(len(ct),dark),boundary_tolerance_mm=.25);cap_count=len(ct);pp.append(cp);tt.append(ct+offset);mm.append(cm);uu.append(np.full(len(ct),-1));cap_proof.update({'triangles':cap_count,'meshing':meshing,'planar_boundary_tolerance_mm':.25})
        else:
            # Hub and support backs remain their earlier complete closed geometry.
            palette=[v or None for v in base['palette'].tolist()];pp=[base['positions_mm']];tt=[base['triangles']];mm=[base['material_ids']];uu=[base['unit_ids']]
        p=np.concatenate(pp);t=np.concatenate(tt);m=np.concatenate(mm);u=np.concatenate(uu);pipeline.save_mesh(target,'candidate',p,t,m,palette,u)
        # Negative ID is explicitly derived geometry, never a native shell identity.
        writer=GlbWriter('Rune flat-back candidate',{'version':'2.0','copyright':'DJI / RoboMaster source geometry and appearance; derived flat rear panel'})
        for unit in np.unique(u):
            ids=u==unit;used,inv=np.unique(t[ids],return_inverse=True);extra={'inspection_only':True,'native_shell_index':int(unit),'derived_geometry':bool(unit<0)}
            if unit<0:extra.update(source_profiles=cap_proof['source_profiles'],profile_producer='native-profile-flat-back-v1')
            writer.add_node('flat-rear-panel' if unit<0 else 'native-shell-'+str(unit),p[used]/1000,inv.reshape(-1,3),[palette[k] for k in m[ids]],extras=extra)
        writer.write(target/'candidate.glb')
        # This list maps only retained original triangles; generated caps use -1 units.
        if arm:
            original_indices=np.load(skins/cid/'retained-triangle-indices.npy')[keep]
        else:original_indices=np.arange(len(base['triangles']))
        np.save(target/'retained-triangle-indices.npy',original_indices)
        row={'id':cid,'before':len(base['triangles']),'after':len(t),'retained_original_triangles':len(original_indices),'cap_triangles':cap_count,'removed_tiny_neutral_shells':removed_hardware,'reference_npz_sha256':digest(path),'reference_glb_sha256':digest(prior/cid/'candidate.glb'),'source_step_sha256':original['original_source_step_sha256'],'selection':original['selection'] if arm else {'scope':'Complete earlier hub/support retained.'},'flat_back':cap_proof,'outputs_sha256':{n:digest(target/n) for n in ['candidate.glb','candidate.npz','retained-triangle-indices.npy']}};results.append(row);print(cid,row['before'],'->',row['after'],'cap',cap_count,flush=True)
    report={'components':results,'before':sum(c['before'] for c in results),'after':sum(c['after'] for c in results),'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_flat_back.py']},'skin_summary_sha256':digest(skins/'summary.json'),'scope':'Flat closed rear visual panels on ten arms: union of two native housing profiles per arm, small holes <17mm filled, large openings kept; projected onto the original main housing rear plane. Directional front/side skin and deliberate tiny neutral hardware omission. Hubs/support remain earlier complete geometry. Derived caps have reserved unit ID -1, not native shell ownership. No watertight/collision claim or installed asset/source modification.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
