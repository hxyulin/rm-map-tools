#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Smooth explicit Rune front panels, tiny bores and shallow target grooves."""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from run import module
from cad_flat_back import flat_back
from cad_visibility_skin import directional_skin,hemisphere_views,raster_owners
from cad_detail_passes import area,mesh_native_detail
from cad_wall_fill import shape_map
from cad_planar_shell import planar_skin
from plan_cad_lods import digest
from validate_parts import read_part
from export_field_package import GlbWriter
from mesh_parts import colour_key
from OCP.TopAbs import TopAbs_SHELL,TopAbs_FACE,TopAbs_REVERSED,TopAbs_WIRE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool,XCAFDoc_ColorSurf,XCAFDoc_ColorGen
from OCP.Quantity import Quantity_Color
from OCP.collections import Sequence_TDF_Label
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--id');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    prior=ROOT/'out/rmuc2027-rune-flat-back';previous=json.loads((prior/'summary.json').read_bytes());source=ROOT/'out/rmuc2027-equipment-pipeline';pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');results=[]
    with tempfile.TemporaryDirectory() as temporary:
        tmp=Path(temporary);helper=tmp/'raster';raster_source=ROOT/'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp';subprocess.run([shutil.which('clang++'),'-O3',str(raster_source),'-o',str(helper)],check=True)
        for previous_component in previous['components']:
            cid=previous_component['id']
            if a.id and cid!=a.id:continue
            target=a.out/cid;target.mkdir(parents=True,exist_ok=True);path=prior/cid/'candidate.npz'
            if digest(path)!=previous_component['outputs_sha256']['candidate.npz']:raise ValueError('input flat-back candidate changed')
            base=np.load(path);p=base['positions_mm'];t=base['triangles'];m=base['material_ids'];u=base['unit_ids'];palette=[v or None for v in base['palette'].tolist()];keep=np.ones(len(t),bool);pp=[p];tt=[];mm=[];uu=[];offset=len(p);derived=[];removed_tiny=[];selection=None
            if '/arm-' in cid:
                front=np.array(previous_component['selection']['front_direction']);step=source/cid/'source.step'
                if digest(step)!=previous_component['source_step_sha256']:raise ValueError('source STEP changed')
                doc,reader,error=read_part(str(step))
                if error:raise ValueError(error)
                labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels);root=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));shells=shape_map(root,TopAbs_SHELL);ct=XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
                # Explicit arm housing/light panel units; no inference across other equipment.
                for unit in [1,2,7,8,9,10,11]:
                    faces=shape_map(shells.FindKey(unit),TopAbs_FACE);entries=[]
                    for index in range(1,faces.Extent()+1):
                        face=TopoDS.Face(faces.FindKey(index));surface=BRepAdaptor_Surface(face)
                        if surface.GetType()!=GeomAbs_Plane:continue
                        plane=surface.Plane();normal=plane.Axis().Direction();n=np.array([normal.X(),normal.Y(),normal.Z()])*(-1 if face.Orientation()==TopAbs_REVERSED else 1)
                        if n@front<.999999:continue
                        color=Quantity_Color();key=None
                        for shape in [face,shells.FindKey(unit),root]:
                            if ct.GetColor(shape,XCAFDoc_ColorSurf,color) or ct.GetColor(shape,XCAFDoc_ColorGen,color):key=colour_key(color);break
                        if key not in palette or key is None:continue
                        point=plane.Location();depth=float(np.array([point.X(),point.Y(),point.Z()])@front);entries.append({'face':face,'index':index,'depth':depth,'material':palette.index(key),'area':area(face),'holes':shape_map(face,TopAbs_WIRE).Extent()-1})
                    # Each material keeps separate shallow depth bands: never flatten a deep recess.
                    for material in sorted({e['material'] for e in entries}):
                        groups=[]
                        for entry in sorted([e for e in entries if e['material']==material],key=lambda e:e['depth']):
                            if not groups or entry['depth']-groups[-1][0]['depth']>1:groups.append([])
                            groups[-1].append(entry)
                        for group in groups:
                            if max(e['area'] for e in group)<500 or not any(e['holes'] for e in group):continue
                            match=(u==unit)&(m==material);g=p[t];depths=g@front;match&=(depths.min(1)>=min(e['depth'] for e in group)-.01)&(depths.max(1)<=max(e['depth'] for e in group)+.01)
                            # Only replace genuinely forward planar source triangles, not groove walls.
                            normals=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);length=np.linalg.norm(normals,axis=1);match&=(normals@front>=.999999*length)&(length>1e-10)
                            if not match.any():continue
                            depth=max(e['depth'] for e in group);cap,proof=flat_back([e['face'] for e in group],-front,-depth,maximum_gap_mm=17)
                            filled=sum(sum(h['filled'] for h in profile['holes']) for profile in proof['profiles'])
                            if not filled and max(e['depth'] for e in group)-min(e['depth'] for e in group)<.01:continue
                            cp,ctri,_,_,mesh=mesh_native_detail(cap,[palette[material]]*shape_map(cap,TopAbs_FACE).Extent(),linear_deflection_mm=.25,angular_deflection_rad=.4);cp,ctri,cm,skin=planar_skin(cp,ctri,np.full(len(ctri),material),boundary_tolerance_mm=.1);new_unit=-2-len(derived)
                            keep[match]=False;pp.append(cp);tt.append(ctri+offset);mm.append(cm);uu.append(np.full(len(ctri),new_unit));offset+=len(cp)
                            derived.append({'unit_id':new_unit,'source_native_shell_index':unit,'shell_local_face_indices':[e['index'] for e in group],'material_id':material,'source_colour':palette[material],'front_direction':front.tolist(),'plane_offset_mm':depth,'maximum_flattened_relief_mm':max(e['depth'] for e in group)-min(e['depth'] for e in group),'removed_planar_triangles':int(match.sum()),'triangles_before_visibility':len(ctri),'filled_small_bores':filled,'native_profiles':proof})
                for unit in np.unique(u[u>=0]):
                    ids=u==unit;positions=p[t[ids]].reshape(-1,3)
                    if np.ptp(positions,axis=0).max()<=17:keep[ids]=False;removed_tiny.append(int(unit))
                # Generated filled front faces now occlude obsolete bore walls/interior.
                full_p=np.concatenate(pp);full_t=np.concatenate([t[keep],*tt]);full_m=np.concatenate([m[keep],*mm]);full_u=np.concatenate([u[keep],*uu]);seen=set()
                for view in hemisphere_views(front):seen.update(map(int,raster_owners(full_p[full_t],view,helper,tmp)))
                selected,selection=directional_skin(full_p,full_t,full_m,full_u,front,np.array(sorted(seen),dtype=np.int64));adopt=np.zeros(len(full_t),bool);adopt[selected]=True;adopt[full_u==-1]=True
                # Keep each generated profile complete, avoiding subpixel sampling holes.
                adopt[full_u< -1]=True
                original_indices=np.flatnonzero(keep)[adopt[:int(keep.sum())]];p=full_p;t=full_t[adopt];m=full_m[adopt];u=full_u[adopt]
            else:original_indices=np.arange(len(t))
            pipeline.save_mesh(target,'candidate',p,t,m,palette,u);np.save(target/'retained-triangle-indices.npy',original_indices)
            writer=GlbWriter('Rune smooth front',{'version':'2.0','copyright':'DJI / RoboMaster geometry/appearance; derived smooth native-profile fronts'})
            for unit in np.unique(u):
                ids=u==unit;used,inv=np.unique(t[ids],return_inverse=True);extra={'native_shell_index':int(unit),'derived_geometry':bool(unit<0),'inspection_only':True}
                if unit< -1:extra['source_profile']=next(d for d in derived if d['unit_id']==unit)['shell_local_face_indices']
                writer.add_node('derived-panel-'+str(unit) if unit<0 else 'native-shell-'+str(unit),p[used]/1000,inv.reshape(-1,3),[palette[k] for k in m[ids]],extras=extra)
            writer.write(target/'candidate.glb');row={'id':cid,'before':previous_component['after'],'after':len(t),'reference_npz_sha256':digest(path),'reference_glb_sha256':digest(prior/cid/'candidate.glb'),'source_step_sha256':previous_component['source_step_sha256'],'generated_unit_ids':[d['unit_id'] for d in derived],'derived_fronts':derived,'removed_tiny_shells':removed_tiny,'selection':previous_component['selection'],'visibility_selection':selection,'outputs_sha256':{name:digest(target/name) for name in ['candidate.glb','candidate.npz','retained-triangle-indices.npy']}};results.append(row);print(cid,row['before'],'->',len(t),'panels',len(derived),flush=True)
    report={'components':results,'before':sum(c['before'] for c in results),'after':sum(c['after'] for c in results),'reference_directory':str(prior.relative_to(ROOT)),'reference_summary_sha256':digest(prior/'summary.json'),'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_flat_back.py',ROOT/'python/cad_visibility_skin.py',raster_source]},'scope':'Explicit front native-profile smoothing on ten arms; holes <17mm filled, <=1mm same-material depth bands flattened, tiny shell detail omitted. Whole native outer wires and large inner openings retained. Flat rear panels and hubs/support unchanged. No runtime/collision/source CAD change.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
