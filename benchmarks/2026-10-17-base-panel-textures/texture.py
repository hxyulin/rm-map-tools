#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Bake the qualified coplanar Base logo into a bounded colour texture patch."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from cad_texture_patch import replace_planar_rectangle,attach_colour_texture
from cad_relief_bake import bake_relief
from export_field_package import GlbWriter
from gltf_scene import read_glb,write_glb
from simplify_package import compact,scene_triangles
from plan_cad_lods import digest
from validate_parts import read_part
from cad_wall_fill import shape_map
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopoDS import TopoDS


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--groove',action='store_true');a=ap.parse_args();source_id=4268930 if a.groove else 4527988;face_id=4202749 if a.groove else 4465456;height_limit=.7 if a.groove else .1;a.out.mkdir(parents=True,exist_ok=True);audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());reference=ROOT/('out/rmuc2027-base-panel-trials/4202749/optimized.npz' if a.groove else 'out/rmuc2027-base-shells-final/geometry.npz');source=ROOT/'out/rmuc2027-base-structure-audit/source.step';d=np.load(reference);i=next(i for i,u in enumerate(audit['units']) if u['source_id']==source_id);mask=d['unit_ids']==i;used,inv=np.unique(d['triangles'][mask],return_inverse=True);p=d['positions_mm'][used];t=inv.reshape(-1,3);c=d['triangle_srgb'][mask];doc,reader,error=read_part(str(source))
    if digest(source)!=audit['component_step_sha256']:raise ValueError('source changed')
    expected=json.loads((reference.parent/'optimization.json').read_bytes())['geometry_sha256'] if a.groove else json.loads((ROOT/'benchmarks/2026-10-17-base-shells/validation.json').read_bytes())['input_sha256']['shells']
    if digest(reference)!=expected:raise ValueError('approved appearance reference changed')
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);ff=shape_map(XCAFDoc_ShapeTool.GetShape_s(roots.Value(1)),TopAbs_FACE);face=TopoDS.Face(ff.FindKey(next(f['native_face_index'] for f in audit['faces'] if f['source_face_id']==face_id)));plane=BRepAdaptor_Surface(face).Plane();o=plane.Location();n=plane.Axis().Direction();origin=np.array([o.X(),o.Y(),o.Z()]);normal=np.array([n.X(),n.Y(),n.Z()]);u=np.array([1.,0,0]);frame=np.array([u,np.cross(normal,u),normal]);bounds=[-400,-44,-210,44] if a.groove else [-105,-75,105,65];local=(p[t]-origin)@frame.T;selected=((local[:,:,2].max(1)<=.1)&(local[:,:,2].min(1)>=-8)) if a.groove else abs(local[:,:,2]).max(1)<=height_limit;v=p[t[selected]].reshape(-1,3);tt=np.arange(len(v)).reshape(-1,3);bake=bake_relief(v,tt,c[selected],origin_mm=origin,axes=frame,bounds_uv_mm=bounds,resolution=1024)
    if bake['metadata']['coverage_fraction']!=1:
        report={'accepted':False,'source_unit_id':source_id,'support_face_id':face_id,'reference_sha256':digest(reference),'bake':bake['metadata'],'reason':'Source projection has uncovered pixels; this rectangle spans openings and is retained as geometry pending finite aperture qualification.','producer_sha256':digest(Path(__file__))};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');Image.fromarray(bake['base_colour_rgba']).save(a.out/'rejected-coverage.png');print(report);return
    result=replace_planar_rectangle(p,t,c,origin_mm=origin,axes=frame,bounds_uv_mm=bounds,height_limit_mm=height_limit);rgba=bake['base_colour_rgba'];padding=8;rgb=np.pad(rgba[:,:,:3],((padding,padding),(padding,padding),(0,0)),mode='edge');Image.fromarray(rgb).save(a.out/'base-logo-colour.png');uv=(result['quad_uv']*1024+padding)/(1024+2*padding);w=GlbWriter('base/textured-logo',{'version':'2.0','copyright':'DJI / RoboMaster source geometry and appearance; derived planar colour bake'});w.add_node('source-unit-'+str(source_id),result['positions_mm']/1000,result['triangles'],[','.join(map(str,col)) for col in result['triangle_srgb']],extras={'source_unit_id':source_id,'inspection_only':True});w.write(a.out/'visual.glb');doc,blob=read_glb(a.out/'visual.glb');blob=attach_colour_texture(doc,blob,node_index=1,positions_m=result['quad_positions_mm']/1000,triangles=result['quad_triangles'],uv=uv,png_bytes=(a.out/'base-logo-colour.png').read_bytes(),metadata={'source_unit_id':source_id,'support_source_face_id':face_id,'height_limit_mm':height_limit,'source_bake_sha256':digest(a.out/'base-logo-colour.png'),'scope':'Coplanar source appearance, not inferred paint or procedural artwork'});blob=compact(doc,blob);write_glb(a.out/'visual.glb',doc,blob);count=scene_triangles(doc);report={'accepted':True,'source_sha256':digest(source),'reference_sha256':digest(reference),'source_unit_id':source_id,'support_face_id':face_id,'groove_trial':a.groove,'before_housing_triangles':len(t),'after_housing_triangles':count,'saved_triangles':len(t)-count,'selected_neutral_artwork_triangles':int((np.all(c==[.6275]*3,axis=1)&selected&np.all((local[:,:,0]>=-105)&(local[:,:,0]<=105)&(local[:,:,1]>=-75)&(local[:,:,1]<=65),axis=1)).sum()),'bake':bake['metadata'],'patch':result['proof'],'texture_pixels':[len(rgb[0]),len(rgb)],'gutter_pixels':padding,'texture_bytes':(a.out/'base-logo-colour.png').stat().st_size,'texture_sha256':digest(a.out/'base-logo-colour.png'),'visual_sha256':digest(a.out/'visual.glb'),'visual_bytes':(a.out/'visual.glb').stat().st_size,'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_texture_patch.py',ROOT/'python/cad_relief_bake.py']},'scope':'Only the explicit bounded front appearance rectangle is flattened. The optional groove trial projects its deeper backing while replacing front surfaces within 0.7 mm; it is independently qualified. Existing outside surfaces retained; colour PNG is sRGB with linear factor one, correct UV V direction and edge gutters. No inferred relief/decal treatment of other source-neutral geometry.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');np.savez(a.out/'patch.npz',positions_mm=result['quad_positions_mm'],triangles=result['quad_triangles'],uv=uv);print({k:report[k] for k in ['before_housing_triangles','after_housing_triangles','saved_triangles','selected_neutral_artwork_triangles','texture_bytes']})
if __name__=='__main__':main()
