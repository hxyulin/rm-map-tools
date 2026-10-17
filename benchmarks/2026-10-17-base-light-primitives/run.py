#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Quad-based source lights and fitted, rear-clipped green icosphere caps."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_light_primitives import rectangle_cover,fit_sphere,icosphere,clip_halfspace
from cad_surface_lods import material_lod
from export_field_package import GlbWriter
from gltf_scene import read_glb,write_glb,accessor
from simplify_package import append_accessor
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--include-rejected',action='store_true');a=ap.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    policy_path=ROOT/'rules/base-light-primitives-rmuc2027.json';policy=json.loads(policy_path.read_bytes());audit=json.loads((a.source/'audit.json').read_bytes());old=json.loads((a.reference/'summary.json').read_bytes())
    if audit['component_step_sha256']!=policy['component_step_sha256'] or digest(a.source/'geometry.npz')!=audit['outputs_sha256']['geometry.npz'] or digest(a.reference/'visual/geometry.npz')!=old['stages']['visual']['geometry_sha256']:raise ValueError('source/reference mismatch')
    original=np.load(a.source/'geometry.npz');base=np.load(a.reference/'visual/geometry.npz');units=audit['units'];red=np.array(policy['red_rgb']);green=np.array(policy['green_rgb']);is_red=np.all(base['triangle_srgb']==red,axis=1);is_green=np.all(base['triangle_srgb']==green,axis=1);report={'component_step_sha256':policy['component_step_sha256'],'policy_sha256':digest(policy_path),'source_audit_sha256':digest(a.source/'audit.json'),'reference_summary_sha256':digest(a.reference/'summary.json'),'reference_triangles':old['stages']['visual']['definition_triangles'],'source_units':len(units),'red_decisions':[],'stages':{},'scope':policy['scope'],'recommended_stage':'ico2','rejected_strategies':{'single-front-quad-for-raised-module':'lost oblique visible light','independent-planar-covers':'dark seams at discarded curved joins','enclosing-boxes':'red protrusions beyond bezels and through rear gaps','ico1':'front green aperture loses 8.55% visible area'}};a.out.mkdir(parents=True)
    replacements={};front_replacements={};box_replacements={}
    for index,u in enumerate(units):
        select=(base['unit_ids']==index)&is_red
        if not select.any():continue
        source=u['source_id'];records=[f for f in audit['faces'] if f['unit']==index and f['source_colour']=='1.0000,0.0000,0.0000'];mask=np.isin(original['source_face_ids'],[f['source_face_id'] for f in records]);source_tri=original['positions_mm'][original['triangles'][mask]];points=np.unique(source_tri.reshape(-1,3),axis=0);pp=[];tt=[];offset=0;proofs=[]
        if max(np.ptp(points,axis=0))<=policy['small_red_box_maximum_span_mm']:
            origin=points.mean(0);_,_,frame=np.linalg.svd(points-origin,full_matrices=False)
            if np.linalg.det(frame)<0:frame[-1]*=-1
            local=(points-origin)@frame.T;lo=local.min(0);hi=local.max(0);p=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])@frame+origin;t=np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]],dtype=np.uint32);pp=[p];tt=[t];proofs=[{'model':'source-oriented-six-quad-box','source_projected_extents_mm':(hi-lo).tolist(),'scope':'Small red surface approximation; not classified as a functional LED from color alone.'}]
        else:
            for record in records:
                if record['surface']!='Plane':continue
                tri=original['positions_mm'][original['triangles'][original['source_face_ids']==record['source_face_id']]];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]).sum(0)
                if np.linalg.norm(normal)<1e-9:continue
                face_points=np.unique(tri.reshape(-1,3),axis=0);_,_,plane_basis=np.linalg.svd(face_points-face_points.mean(0),full_matrices=False);fit_normal=plane_basis[-1]
                if fit_normal@normal<0:fit_normal=-fit_normal
                q,t,proof=rectangle_cover(face_points,fit_normal,inset_mm=policy['planar_cover_inset_mm'],padding_mm=policy['planar_cover_padding_mm']);pp.append(q);tt.append(t+offset);offset+=len(q);proofs.append({'source_face_id':record['source_face_id'],'source_area_mm2':record['area_mm2'],'proof':proof})
        if pp:
            replacements[source]=(np.concatenate(pp),np.concatenate(tt));
            if 'source-oriented-six-quad-box'==proofs[0].get('model'):front_replacements[source]=replacements[source]
            else:
                j=max(range(len(proofs)),key=lambda k:proofs[k]['source_area_mm2']*proofs[k]['proof']['outward_normal'][1]);front_replacements[source]=(pp[j],np.array([[0,1,2],[0,2,3]],dtype=np.uint32));proofs[j]['selected_front_quad']=True
            if proofs[0].get('model')=='source-oriented-six-quad-box':box_replacements[source]=replacements[source]
            else:
                j=max(range(len(proofs)),key=lambda k:proofs[k]['source_area_mm2']);quad=pp[j];x=(quad[1]-quad[0]);x/=np.linalg.norm(x);y=(quad[3]-quad[0]);y/=np.linalg.norm(y);normal=np.cross(x,y);frame=np.array([x,y,normal]);origin=points.mean(0);local=(points-origin)@frame.T;lo=local.min(0);hi=local.max(0)
                bp=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])@frame+origin;bt=np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]],dtype=np.uint32);box_replacements[source]=(bp,bt);proofs[j]['box_frame_source_face']=True;proofs[j]['box_extents_mm']=(hi-lo).tolist()
            report['red_decisions'].append({'source_unit_id':source,'before_triangles':int(select.sum()),'after_triangles':sum(len(x) for x in tt),'recipes':proofs,'source_face_ids':[r['source_face_id'] for r in records]})
    safe={};mixed={};report['bounded_red_lod_decisions']=[]
    for decision in report['red_decisions']:
        source=decision['source_unit_id'];index=next(i for i,u in enumerate(units) if u['source_id']==source)
        if str(source) in policy['front_quad_faces_by_source_unit']:
            recipe=next(x for x in decision['recipes'] if x.get('source_face_id')==policy['front_quad_faces_by_source_unit'][str(source)]);tri=original['positions_mm'][original['triangles'][original['source_face_ids']==recipe['source_face_id']]];q,t,proof=rectangle_cover(np.unique(tri.reshape(-1,3),axis=0),recipe['proof']['outward_normal']);safe[source]=(q,t);mixed[source]=(q,t);report['bounded_red_lod_decisions'].append({'source_unit_id':source,'model':'exact-front-rectangle','source_face_id':recipe['source_face_id'],'proof':proof})
        else:
            ids=decision['source_face_ids'];tri=original['positions_mm'][original['triangles'][np.isin(original['source_face_ids'],ids)]];p=tri.reshape(-1,3);t=np.arange(len(p)).reshape(-1,3)
            try:
                p,t,_,proof=material_lod(p,t,np.zeros(len(t),dtype=np.int32),error_mm=policy['remaining_red_error_mm'],sampled_limit_mm=policy['remaining_red_sampled_limit_mm'],sample_count=4096);old_count=int(((base['unit_ids']==index)&is_red).sum())
                if len(t)<old_count:mixed[source]=(p,t);report['bounded_red_lod_decisions'].append({'source_unit_id':source,'model':'bounded-source-light-lod','before_triangles':old_count,'after_triangles':len(t),'proof':proof})
                else:report['bounded_red_lod_decisions'].append({'source_unit_id':source,'model':'retain-approved','reason':'no triangle saving'})
            except ValueError as e:report['bounded_red_lod_decisions'].append({'source_unit_id':source,'model':'retain-approved','reason':str(e)})
    optic=policy['optic_source_unit_id'];optic_index=next(i for i,u in enumerate(units) if u['source_id']==optic);sphere_faces=[f['source_face_id'] for f in audit['faces'] if f['unit']==optic_index and f['source_colour']=='0.0650,0.9810,0.0620'];mask=np.isin(original['source_face_ids'],sphere_faces);tri=original['positions_mm'][original['triangles'][mask]];source_points=np.unique(tri.reshape(-1,3),axis=0);center,radius,fit=fit_sphere(source_points,maximum_residual_mm=policy['optic_sphere_vertex_fit_limit_mm'])
    # Tolerance-key welding discovers only the cap boundary. Fitting retains the
    # original source coordinates, not the quantized keys.
    p=original['positions_mm'];t=original['triangles'][mask];used,inv=np.unique(t,return_inverse=True);local=p[used];_,first,weld=np.unique(np.round(local,5),axis=0,return_index=True,return_inverse=True);faces=weld[inv.reshape(-1,3)];edges=np.sort(np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1);edges,counts=np.unique(edges,axis=0,return_counts=True);boundary=local[first[np.unique(edges[counts==1])]];boundary_center=boundary.mean(0);_,_,basis=np.linalg.svd(boundary-boundary_center,full_matrices=False);axis=basis[-1]
    if np.dot(axis,source_points.mean(0)-center)<0:axis=-axis
    if max(abs((boundary-boundary_center)@axis))>1e-4:raise ValueError('source optic boundary is not one planar aperture')
    plane=float(boundary_center@axis);clip=plane-policy['optic_hidden_extension_mm'];report['optic']={'source_face_ids':sphere_faces,'fit':fit,'aperture_axis':axis.tolist(),'aperture_plane_offset_mm':plane,'hidden_clip_offset_mm':clip,'boundary_plane_residual_mm':float(max(abs((boundary-boundary_center)@axis))),'scope':'Rear-clipped open spherical cap; full fitted sphere is deliberately not exported through the housing.'}
    def save():
        report['producer_sha256']={str(p.relative_to(ROOT)):digest(p) for p in (Path(__file__),ROOT/'python/cad_light_primitives.py')};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    def write(stage,sphere=None,*,front_only=False,box_only=False,custom_replacements=None):
        selected_replacements=custom_replacements if custom_replacements is not None else box_replacements if box_only else front_replacements if front_only else replacements
        folder=a.out/stage;folder.mkdir();writer=GlbWriter('base/'+stage,{'version':'2.0','copyright':'DJI / RoboMaster source geometry; fitted light primitive candidate'});pp=[];tt=[];cc=[];ff=[];uu=[];normals=[];offset=0;light_count=0;protected=0
        for index,u in enumerate(units):
            source=u['source_id'];select=base['unit_ids']==index;old_tri=base['positions_mm'][base['triangles'][select]];old_c=base['triangle_srgb'][select];light=np.all(old_c==red,axis=1);change_red=source in selected_replacements;change_green=sphere is not None and source==optic;keep=~light if change_red else np.ones(len(old_tri),dtype=bool)
            if change_green:keep&=~np.all(old_c==green,axis=1)
            points=[old_tri[keep].reshape(-1,3)];triangles=[np.arange(keep.sum()*3).reshape(-1,3)];colours=[old_c[keep]];ids=[base['source_face_ids'][select][keep]];at=len(points[0])
            if change_red:
                p,t=selected_replacements[source];points.append(p);triangles.append(t+at);at+=len(p);colours.append(np.tile(red,(len(t),1)));ids.append(np.zeros(len(t),dtype=np.uint32))
            if change_green:
                p,t=sphere;points.append(p);triangles.append(t+at);colours.append(np.tile(green,(len(t),1)));ids.append(np.zeros(len(t),dtype=np.uint32))
            p=np.concatenate(points);t=np.concatenate(triangles);c=np.concatenate(colours);f=np.concatenate(ids);writer.add_node('source-unit-'+str(source),p/1000,t,[','.join(f'{x:.4f}' for x in col) for col in c],extras={'source_unit_id':source,'inspection_only':True,'light_primitive_candidate':change_red or change_green});pp.append(p);tt.append(t+offset);offset+=len(p);cc.append(c);ff.append(f);uu.extend([index]*len(t));n=np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]]);n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-30);vn=np.repeat(n[:,None,:],3,axis=1)
            if change_green:
                green_mask=np.all(c==green,axis=1);radial=p[t[green_mask]]-center;radial/=np.linalg.norm(radial,axis=2)[:,:,None];vn[green_mask]=radial
            normals.append(vn);light_count+=int((np.all(c==red,axis=1)|np.all(c==green,axis=1)).sum())
            original_keep=~(np.all(old_c==red,axis=1)|np.all(old_c==green,axis=1));new_keep=~(np.all(c==red,axis=1)|np.all(c==green,axis=1))
            if not np.array_equal(p[t[new_keep]],old_tri[original_keep]) or not np.array_equal(c[new_keep],old_c[original_keep]):raise ValueError('non-light geometry changed')
            protected+=int(new_keep.sum())
        writer.write(folder/'visual.glb')
        if sphere is not None:
            doc,binary=read_glb(folder/'visual.glb');binary=bytearray(binary)
            for node in doc['nodes']:
                if node.get('extras',{}).get('source_unit_id')!=optic:continue
                for primitive in doc['meshes'][node['mesh']]['primitives']:
                    colour=doc['materials'][primitive['material']]['extras']['step_colour_srgb']
                    if not np.allclose(colour,green,atol=1e-8,rtol=0):continue
                    p=accessor(doc,binary,primitive['attributes']['POSITION']).astype(float)*1000;radial=p-center;radial/=np.linalg.norm(radial,axis=1)[:,None];primitive['attributes']['NORMAL']=append_accessor(doc,binary,np.asarray(radial,dtype='<f4'),'VEC3',5126)
            doc['buffers'][0]['byteLength']=len(binary);write_glb(folder/'visual.glb',doc,bytes(binary))
        np.savez(folder/'geometry.npz',positions_mm=np.concatenate(pp),triangles=np.concatenate(tt),triangle_srgb=np.concatenate(cc),source_face_ids=np.concatenate(ff),unit_ids=np.asarray(uu,dtype=np.uint32),triangle_vertex_normals=np.concatenate(normals))
        total=sum(len(t) for t in tt);report['stages'][stage]={'definition_triangles':total,'placed_triangles':2*total,'light_triangles':light_count,'byte_exact_non_light_triangles':protected,'visual_sha256':digest(folder/'visual.glb'),'geometry_sha256':digest(folder/'geometry.npz'),'sphere_triangles':len(sphere[1]) if sphere else 0};save();print(stage,total,'triangles, lights',light_count,flush=True)
    if a.include_rejected:
        write('quads')
        write('boxes',box_only=True)
        write('front-quads',front_only=True)
    write('strips',custom_replacements=safe)
    for level in policy['optic_icosphere_subdivisions']:
        p,t=icosphere(level);p=p*radius+center;p,t=clip_halfspace(p,t,axis,clip);write('ico'+str(level),(p,t),custom_replacements=mixed)
    save()


if __name__=='__main__':main()
