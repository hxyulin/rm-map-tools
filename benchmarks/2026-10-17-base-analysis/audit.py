#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only RMUC 2027 Base native face/body/shell cost and spatial audit."""
import argparse
from collections import Counter,defaultdict
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_document import CadDocument
from p21split import Splitter
from plan_cad_lods import digest,build_plan
from validate_parts import read_part
from mesh_parts import tessellate
from export_field_package import GlbWriter
from cad_wall_fill import shape_map
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.STEPConstruct import STEPConstruct
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--hierarchy',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    started=time.perf_counter();h=json.loads(a.hierarchy.read_bytes());c=next(c for c in h['components'] if c['id']=='base/source-model');hierarchy_sha=digest(a.hierarchy)
    a.out.mkdir(parents=True)
    with CadDocument.from_step(a.source,workers=1,intern_layers=True,expected_sha256=h['files_sha256']['field.step']) as cad:
        splitter=Splitter(cad.index,cad.model);mask,rewrite=splitter.closure_products([cad.index.r(c['export_product_id'])]);splitter.write_closure(mask,rewrite,a.out/'source.step');cad.verify_source()
    print('Base STEP extracted',flush=True)
    with CadDocument.from_step(a.out/'source.step',workers=1,intern_layers=True) as cad:
        ix=cad.index;native,reader,error=read_part(str(a.out/'source.step'))
        if error:raise ValueError(error)
        tool=XCAFDoc_DocumentTool.ShapeTool_s(native.Main());roots=Sequence_TDF_Label();tool.GetFreeShapes(roots)
        if roots.Length()!=1:raise ValueError('expected one Base definition root')
        shape=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));fmap=shape_map(shape,TopAbs_FACE)
        source_by_native={};process=reader.Reader().WS().MapReader();model=reader.Reader().StepModel()
        if model.NbEntities()!=ix.n:raise ValueError('native/source record order mismatch')
        for source in c['face_ids']:
            row=ix.r(source);entity=model.Value(row+1)
            if entity.DynamicType().Name()!='StepShape_AdvancedFace':raise ValueError('native/source face type mismatch')
            face=STEPConstruct.FindShape_s(process,entity);index=fmap.FindIndex(face)
            if not index or index in source_by_native:raise ValueError('source/native face identity is not bijective')
            source_by_native[index]=source
        if len(source_by_native)!=fmap.Extent():raise ValueError('native/source face coverage incomplete')
        units=[];unit_of_face={}
        def add_unit(kind,source,faces):
            index=len(units)
            for face in faces:
                if face in unit_of_face:raise ValueError('source face belongs to several selected units')
                unit_of_face[face]=index
            units.append({'kind':kind,'source_id':source,'face_ids':faces,'faces':len(faces)})
        for body in c['solid_body_ids']:add_unit('solid',body,[int(ix.ids[r]) for r in cad.model.body_faces(ix.r(c['export_body_ids'][str(body)]))])
        for body,shells in c['shell_ids_by_body'].items():
            for shell in shells:add_unit('surface-shell',shell,list(map(int,ix.refs_of(ix.r(shell)))))
        if set(unit_of_face)!=set(c['face_ids']):raise ValueError('source unit coverage mismatch')
        records=[];stats={}
        def observe(i,face,count):
            source=source_by_native[i];surface=BRepAdaptor_Surface(face);kind=str(surface.GetType()).rsplit('_',1)[-1]
            props=GProp_GProps();BRepGProp.SurfaceProperties_s(face,props)
            item={'source_face_id':source,'native_face_index':i,'unit':unit_of_face[source],'surface':kind,'triangles':count,'area_mm2':props.Mass()}
            if kind=='Cylinder':item['radius_mm']=surface.Cylinder().Radius()
            records.append(item)
        print('Source-native face binding verified; meshing',flush=True)
        positions,triangles,ci,colors=tessellate(native,.4,.25,stats,observe)
        if stats.get('unmeshed_faces') or len(records)!=len(source_by_native):raise ValueError('incomplete Base tessellation')
        face_ids=[];unit_ids=[];offset=0;by_surface=Counter();by_colour=Counter()
        for f in records:
            count=f['triangles'];t=triangles[offset:offset+count];offset+=count
            f['bbox_mm']=[positions[t].min((0,1)).tolist(),positions[t].max((0,1)).tolist()] if count else None
            selected={colors[int(i)] for i in ci[offset-count:offset]}
            if len(selected)!=1:raise ValueError('missing/ambiguous per-face diffuse')
            f['source_colour']=next(iter(selected));by_surface[f['surface']]+=count;by_colour[str(f['source_colour'])]+=count
            face_ids.extend([f['source_face_id']]*count);unit_ids.extend([f['unit']]*count)
        if offset!=len(triangles):raise ValueError('face triangle accounting mismatch')
        unit_ids=np.array(unit_ids,dtype=np.uint32);face_ids=np.array(face_ids,dtype=np.uint32)
        for i,u in enumerate(units):
            selected=unit_ids==i;p=positions[triangles[selected]];faces=[f for f in records if f['unit']==i]
            u.update({'triangles':int(selected.sum()),'bbox_mm':[p.min((0,1)).tolist(),p.max((0,1)).tolist()],
                      'surface_triangles':dict(sum((Counter({f['surface']:f['triangles']}) for f in faces),Counter())),
                      'unresolved_diffuse_triangles':sum(f['triangles'] for f in faces if f['source_colour'] is None)})
        writer=GlbWriter('base/source-model',{'version':'2.0','copyright':'DJI / RoboMaster original source geometry; read-only native audit'})
        writer.add_node('base/source-model',positions/1000,triangles,[colors[int(i)] for i in ci]);writer.write(a.out/'source.glb')
        rgb=np.array([[float(v) for v in key.split(',')] if key else [.6275]*3 for key in colors])
        np.savez(a.out/'geometry.npz',positions_mm=positions,triangles=triangles,source_face_ids=face_ids,unit_ids=unit_ids,colour_indices=ci,source_srgb=rgb)
        cad.verify_source()
    uses=[n for n in build_plan(h)['nodes'] if n['component_id']==c['id']]
    result={'source_sha256':h['files_sha256']['field.step'],'hierarchy_sha256':hierarchy_sha,'component_step_sha256':digest(a.out/'source.step'),
            'component_id':c['id'],'source_product_id':c['source_product_id'],'source_faces':len(c['face_ids']),'native_faces':fmap.Extent(),
            'source_native_binding':'Complete bijection from STEP transfer face identities; native record count and face types checked. Original source IDs retained.',
            'source_units':len(units),'solid_units':len(c['solid_body_ids']),'surface_shell_units':sum(len(s) for s in c['shell_ids_by_body'].values()),
            'definition_triangles':len(triangles),'placed_uses':len(uses),'placed_triangles':len(triangles)*len(uses),
            'tessellation':{'linear_deflection_mm':.4,'angular_deflection_rad':.25},'tessellation_stats':stats,
            'triangles_by_surface':dict(by_surface),'triangles_by_diffuse':dict(by_colour),'units':units,'faces':records,
            'bbox_mm':[positions.min(0).tolist(),positions.max(0).tolist()],'placements':uses,'source_unchanged':True,
            'producer_sha256':digest(Path(__file__)),'outputs_sha256':{name:digest(a.out/name) for name in ['source.step','source.glb','geometry.npz']},'elapsed_seconds':time.perf_counter()-started,
            'scope':'Read-only original Base, source pose. No reconstruction, visibility pruning, simplification, new functional/motion bindings or runtime replacement.'}
    if digest(a.hierarchy)!=hierarchy_sha:raise ValueError('hierarchy changed')
    (a.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('units','faces','placements')},indent=2),flush=True)
if __name__=='__main__':main()
