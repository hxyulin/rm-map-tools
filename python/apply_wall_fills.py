#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Apply checksum-pinned native wall profiles to derived component definitions.

Source faces stay immutable. Generated replacement solids retain a correspondence
ledger and must be reviewed before any runtime package is promoted.
"""
import argparse
from collections import Counter
import hashlib,json
from pathlib import Path
import numpy as np
from cad_document import CadDocument
from cad_wall_fill import FaceProfilePanel,fill_wall,shape_map,volume
from p21split import Splitter
from plan_cad_lods import build_plan
from mesh_parts import tessellate
from validate_parts import read_part
from export_field_package import GlbWriter


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def native_shape(doc):
    from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
    from OCP.collections import Sequence_TDF_Label
    from OCP.TopAbs import TopAbs_SOLID
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots)
    if roots.Length()!=1:raise ValueError('expected one component definition root')
    solids=shape_map(XCAFDoc_ShapeTool.GetShape_s(roots.Value(1)),TopAbs_SOLID)
    if solids.Extent()!=1:raise ValueError('expected one component solid')
    return solids.FindKey(1)


def mesh(doc,name,path):
    observed=[];stats={}
    p,t,ci,keys=tessellate(doc,.4,.25,stats,lambda i,f,n:observed.append((f,n)))
    if stats.get('unmeshed_faces'):raise ValueError('incomplete wall mesh')
    colours=[];start=0
    for _,count in observed:
        values={keys[int(i)] for i in ci[start:start+count]};start+=count
        if len(values)!=1:raise ValueError('native face has missing/ambiguous material')
        colours.append(next(iter(values)))
    writer=GlbWriter(name,{'version':'2.0','copyright':'DJI / RoboMaster source geometry; reviewed derived wall fill'})
    writer.add_node(name,p/1000,t,[keys[int(i)] for i in ci],extras={'inspection_only':True});writer.write(path)
    return observed,colours,{'triangles':len(t),'faces':len(observed),'bbox_mm':[p.min(0).tolist(),p.max(0).tolist()],
                            'face_colours':dict(Counter(str(c) for c in colours)),'sha256':sha(path),'stats':stats}


def result_document(result):
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ColorSurf
    from OCP.Quantity import Quantity_Color,Quantity_TOC_sRGB
    from OCP.TopAbs import TopAbs_FACE
    doc=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).AddShape(result.shape,False)
    tool=XCAFDoc_DocumentTool.ColorTool_s(doc.Main());faces=shape_map(result.shape,TopAbs_FACE)
    for i,key in enumerate(result.face_colours,1):
        if key is not None:tool.SetColor(faces.FindKey(i),Quantity_Color(*map(float,key.split(',')),Quantity_TOC_sRGB),XCAFDoc_ColorSurf)
    return doc


def run(source,hierarchy,policy_path,out):
    from OCP.TopAbs import TopAbs_FACE,TopAbs_WIRE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    policy=json.loads(policy_path.read_bytes());catalog=json.loads(hierarchy.read_bytes())
    if out.exists():raise FileExistsError(out)
    if policy['schema']!='rm-native-wall-fill-policy-v1' or sha(hierarchy)!=policy['hierarchy_sha256']:raise ValueError('wall hierarchy/policy mismatch')
    components={c['id']:c for c in catalog['components']};records=[]
    placed=Counter(n['component_id'] for n in build_plan(catalog)['nodes'] if n['component_id'])
    ids=[e['component_id'] for e in policy['components']]
    if len(set(ids))!=len(ids):raise ValueError('duplicate component wall selections')
    if any(e['placed_uses']!=placed[e['component_id']] for e in policy['components']):raise ValueError('wall placement accounting changed')
    with CadDocument.from_step(source,workers=1,expected_sha256=policy['source_sha256'],intern_layers=True) as cad:
        if cad.source_sha256!=catalog['files_sha256']['field.step']:raise ValueError('source/hierarchy mismatch')
        out.mkdir(parents=True);splitter=Splitter(cad.index,cad.model)
        for entry in policy['components']:
            c=components[entry['component_id']];name=c['id'].split('/')[0];folder=out/name;folder.mkdir()
            mask,rewrite=splitter.closure_products([cad.index.r(c['export_product_id'])]);splitter.write_closure(mask,rewrite,folder/'source.step')
            if sha(folder/'source.step')!=entry['component_step_sha256']:raise ValueError('source component checksum changed; review selectors')
            doc,reader,error=read_part(str(folder/'source.step'))
            if error:raise ValueError(error)
            shape=native_shape(doc);faces=shape_map(shape,TopAbs_FACE)
            observed,colours,before=mesh(doc,name,folder/'source.glb')
            if faces.Extent()!=entry['expected_source_faces'] or len(observed)!=faces.Extent() or any(not faces.FindKey(i).IsSame(f) for i,(f,_) in enumerate(observed,1)):
                raise ValueError('source face index/mesh correspondence mismatch')
            spec=entry['profile'];index=spec['native_face_index'];face=TopoDS.Face(faces.FindKey(index));surface=BRepAdaptor_Surface(face)
            props=GProp_GProps();BRepGProp.SurfaceProperties_s(face,props)
            if abs(props.Mass()-spec['expected_area_mm2'])>.001 or shape_map(face,TopAbs_WIRE).Extent()!=spec['expected_wires']:
                raise ValueError('source profile signature changed')
            normal=surface.Plane().Axis().Direction()
            if np.max(abs(np.array([normal.X(),normal.Y(),normal.Z()])-spec['expected_normal']))>1e-10:raise ValueError('source profile normal changed')
            result=fill_wall(shape,FaceProfilePanel(face,spec['depth_mm'],colours[index-1],spec['mode'],spec.get('window_uv_mm')),colours,
                             max_added_volume_mm3=entry['max_added_volume_mm3'])
            candidate=result_document(result);writer=STEPCAFControl_Writer();writer.SetColorMode(True);writer.SetNameMode(True)
            if not writer.Transfer(candidate,STEPControl_AsIs) or writer.Write(str(folder/'candidate.step'))!=IFSelect_RetDone:raise ValueError('wall STEP export failed')
            loaded,reader,error=read_part(str(folder/'candidate.step'))
            if error:raise ValueError(error)
            _,loaded_colours,after=mesh(loaded,name,folder/'candidate.glb');reloaded=native_shape(loaded)
            if after['faces']!=result.proof['result_faces'] or abs(volume(reloaded)-volume(result.shape))>.01 or Counter(loaded_colours)!=Counter(result.face_colours):
                raise ValueError('derived STEP roundtrip changed face, volume or appearance accounting')
            record={'component_id':c['id'],'source_sha256':cad.source_sha256,'component_step_sha256':entry['component_step_sha256'],
                    'source_face_ids':c['face_ids'],'profile':spec,'before':before,'after':after,'proof':result.proof,
                    'derived_step_sha256':sha(folder/'candidate.step'),'output_native_face_ledger':[{'face':i,'source_native_faces':list(ids),'panel_generated':not ids,'source_colour':key}
                      for i,(ids,key) in enumerate(zip(result.source_face_indices,result.face_colours),1)],
                    'ledger_scope':'Native result faces before STEP serialization; source-native indices qualified by component_step_sha256. STEP roundtrip may reorder faces.',
                    'source_unresolved_appearance_preserved':None in colours,'placed_uses':entry['placed_uses']}
            records.append(record);(folder/'report.json').write_text(json.dumps(record,indent=2)+'\n')
            print(name,before['triangles'],'->',after['triangles'],'triangles',flush=True)
        cad.verify_source()
    summary={'schema':'rm-wall-fill-review-v1','source_sha256':policy['source_sha256'],'hierarchy_sha256':sha(hierarchy),'policy_sha256':sha(policy_path),
             'tessellation':{'linear_deflection_mm':.4,'angular_deflection_rad':.25},'components':records,
             'definition_triangles_before':sum(r['before']['triangles'] for r in records),'definition_triangles_after':sum(r['after']['triangles'] for r in records),
             'placed_triangles_before':sum(r['before']['triangles']*r['placed_uses'] for r in records),'placed_triangles_after':sum(r['after']['triangles']*r['placed_uses'] for r in records),
             'source_unchanged':True,'runtime_installed':False,'scope':'Only selected definitions and original placed-use counts; additive aperture closure, not lossless geometry or whole-arena savings.',
             'producer_sha256':{name:sha(Path(__file__).with_name(name)) for name in ['cad_wall_fill.py','apply_wall_fills.py']}}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--hierarchy',type=Path,required=True);p.add_argument('--policy',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.source,a.hierarchy,a.policy,a.out)
