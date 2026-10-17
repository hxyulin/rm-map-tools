#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Export a complete source-bound planar/extruded component for review."""
import argparse
from collections import Counter
import hashlib,json,shutil,time
from pathlib import Path
import numpy as np
from cad_document import CadDocument
from cad_component import NativeComponent
from cad_component_mesh import vector_component_mesh
from p21split import Splitter


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_supports(component,positions,triangles,face_ids,limit_mm):
    """Check deterministic vertices/edge midpoints/centroids on every native face.

    These are sampled support distances, not a continuous Hausdorff certificate
    or a bidirectional trim-domain test. The shared incidence test is separate.
    """
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS
    from OCP.BRepTools import BRepTools
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt
    maximum=0.;count=0;per_face={}
    for face_id in sorted(set(map(int,face_ids))):
        face=TopoDS.Face(component.shapes[face_id]);surface=BRep_Tool.Surface_s(face);bounds=BRepTools.UVBounds_s(face)
        selected=triangles[face_ids==face_id]
        corners=positions[selected];samples=np.concatenate((positions[np.unique(selected)],corners.mean(axis=1),
                              (corners[:,0]+corners[:,1])/2,(corners[:,1]+corners[:,2])/2,(corners[:,2]+corners[:,0])/2))
        worst=0.
        for p in samples:
            projection=GeomAPI_ProjectPointOnSurf(gp_Pnt(*p),surface,*bounds,1e-9)
            if projection.NbPoints()==0:raise ValueError('native surface projection failed')
            worst=max(worst,float(projection.LowerDistance()))
        if worst>limit_mm:raise ValueError(f'face #{face_id} support deviation {worst} exceeds {limit_mm} mm')
        maximum=max(maximum,worst);count+=len(samples);per_face[face_id]=worst
    return {'sampled_support_points':count,'max_sampled_native_surface_distance_mm':maximum,
            'max_sampled_distance_by_source_face_mm':per_face,
            'scope':'deterministic vertex/triangle-center/edge-midpoint distances to bounded native supports; not a continuous or bidirectional trim certificate'}


def face_colours(component):
    from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ColorSurf,XCAFDoc_ColorGen,XCAFDoc_ShapeTool
    from OCP.collections import Sequence_TDF_Label
    from OCP.Quantity import Quantity_Color
    from validate_parts import colour_key
    from mesh_parts import _instance_face_colours
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_FACE
    tool=XCAFDoc_DocumentTool.ShapeTool_s(component.native_document.Main());ct=XCAFDoc_DocumentTool.ColorTool_s(component.native_document.Main())
    roots=Sequence_TDF_Label();tool.GetFreeShapes(roots);faces=IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher();TopExp.MapShapes_s(component.shape,TopAbs_FACE,faces)
    inherited=_instance_face_colours(roots,faces,ct);color=Quantity_Color();body=None
    for shape in [component.shape]+[XCAFDoc_ShapeTool.GetShape_s(roots.Value(i)) for i in range(1,roots.Length()+1)]:
        if ct.GetColor(shape,XCAFDoc_ColorSurf,color) or ct.GetColor(shape,XCAFDoc_ColorGen,color):body=colour_key(color);break
    result={}
    for record in component.graph['faces']:
        source=record['source_face_id'];shape=component.shapes[source]
        direct=colour_key(color) if (ct.GetColor(shape,XCAFDoc_ColorSurf,color) or ct.GetColor(shape,XCAFDoc_ColorGen,color)) else None
        result[source]=direct or inherited.get(faces.FindIndex(shape)) or body
    return result


DEFAULT_ROLES=Path(__file__).resolve().parents[1]/'rules/roles-rmuc2027-terrain.json'


def build(source,hierarchy,output,*,component_id='red-road-surface/body-3789460',quality_mm=.1,roles=DEFAULT_ROLES):
    if output.exists():raise FileExistsError(output)
    before=time.perf_counter();catalog=json.loads(hierarchy.read_text())
    from cad_collision_roles import CollisionRoles
    role_policy=CollisionRoles.read(roles,hierarchy)
    role_binding=role_policy.binding(component_id)
    record=next(c for c in catalog['components'] if c['id']==component_id)
    if len(record['export_body_ids'])!=1:raise ValueError('one source body required')
    body_id=next(iter(record['export_body_ids'].values()))
    output.mkdir(parents=True)
    with CadDocument.from_step(source,workers=1,intern_layers=True) as document:
        if catalog['files_sha256']['field.step']!=document.source_sha256:raise ValueError('hierarchy/source checksum mismatch')
        parent_sha=document.source_sha256;splitter=Splitter(document.index,document.model)
        mask,rewritten=splitter.closure_products([document.index.r(record['export_product_id'])])
        splitter.write_closure(mask,rewritten,output/'source.step');document.verify_source()
    with NativeComponent(output/'source.step',body_id) as component:
        fallback_reason=None
        try:
            points,triangles,face_ids,proof=vector_component_mesh(component,quality_mm)
            checks=validate_supports(component,points,triangles,face_ids,quality_mm)
        except ValueError as error:
            fallback_reason=str(error);points,triangles,face_ids,proof=component.mesh(quality_mm,.2)
            local=points-points.mean(axis=0)
            proof['volume_mm3']=abs(float(np.sum(local[triangles[:,0]]*np.cross(local[triangles[:,1]],local[triangles[:,2]]))/6))
            checks=validate_supports(component,points,triangles,face_ids,quality_mm)
        proof['backend']='source-native-fallback' if fallback_reason else 'shared-vector-boundaries'
        proof['fallback_reason']=fallback_reason
        baseline_points,baseline_triangles,_,baseline=component.mesh(quality_mm,.2)
        local=baseline_points-baseline_points.mean(axis=0);a,b,c=local[baseline_triangles[:,0]],local[baseline_triangles[:,1]],local[baseline_triangles[:,2]]
        baseline_volume=float(np.sum(a*np.cross(b,c))/6)
        checks['native_mesh_volume_mm3']=baseline_volume
        checks['volume_reference']='closed native tessellation; not adaptive kernel integration of periodic supports'
        colours=face_colours(component)
        graph={**component.graph,'parent_source_sha256':parent_sha,'component_id':component_id,
               'source_step_sha256':sha(output/'source.step'),'native_binding':component.proof,
               'semantic_roles':role_binding,'roles_sha256':sha(roles),
               'source_geometry_notice':'DJI / RoboMaster geometry; source terms and ownership unchanged; see NOTICE.md.'}
        with (output/'component.json').open('x') as stream:json.dump(graph,stream,indent=2,allow_nan=False);stream.write('\n')
        origin=(points.min(axis=0)+points.max(axis=0))/2
        from export_field_package import GlbWriter
        asset={'version':'2.0','generator':'rm-map-tools source-bound vector component',
               'copyright':'Source CAD: DJI / RoboMaster; see NOTICE.md',
               'extras':{'coordinate_frame':'local source CAD axes, Z up; metre-space geometry','source_component':component_id}}
        writer=GlbWriter('ROAD-SOURCE-COMPONENT',asset)
        writer.add_node('complete-source-solid',(points-origin)/1000,triangles,[colours[int(f)] for f in face_ids],
                        extras={'source_body_id':body_id,'source_local_origin_mm':origin.tolist(),
                                'rm':{'role':'marking' if role_binding and role_binding['selection']=='component' else
                                             'structure-with-markings' if role_binding else 'unclassified',
                                      'collision':role_policy.collision_enabled(component_id)}})
        for primitive,key in zip(writer.meshes[0]['primitives'],sorted(set(colours.values()),key=lambda k:(k is None,k))):
            primitive['extras']={'source_face_ids':[int(f) for f in face_ids if colours[int(f)]==key]}
        writer.write(output/'visual.glb')
        partition=role_policy.partition(component_id,face_ids)
        collision_indices=np.array(partition['collision'],dtype=np.int64)
        collision_triangles=triangles[collision_indices]
        collision=GlbWriter('ROAD-COLLISION',asset)
        collision.add_node('complete-source-solid',(points-origin)/1000,collision_triangles,[None]*len(collision_triangles),
                           extras={'source_body_id':body_id,'collision':bool(len(collision_triangles)),
                                   'unpainted_backing_triangles':len(partition['unpainted_backing'])})
        if collision.meshes:
            collision.meshes[0]['primitives'][0]['extras']={'source_face_ids':face_ids[collision_indices].tolist()}
        collision.write(output/'collision.glb')
        np.savez_compressed(output/'geometry.npz',positions_mm=points,triangles=triangles,source_face_ids=face_ids,
                            baseline_positions_mm=baseline_points,baseline_triangles=baseline_triangles,collision_triangles=collision_triangles)
        float32_points=((points-origin)/1000).astype(np.float32).astype(float)*1000+origin
        quantization=float(np.linalg.norm(float32_points-points,axis=1).max())
        if checks['max_sampled_native_surface_distance_mm']+quantization>quality_mm:raise ValueError('GLB quantization exceeds sampled source-support margin')
        component.document.verify_source()
        report={'software_license':'MIT OR Apache-2.0 (tooling only)','source_sha256':parent_sha,'component_id':component_id,
                'scope':'one complete closed source road-profile solid, not the whole multi-component road assembly or an installed runtime replacement',
                'native_binding':component.proof,'vector_mesh':proof,'native_mesh_baseline':baseline,'native_support_validation':checks,
                'volume_relative_difference':abs(proof['volume_mm3']/checks['native_mesh_volume_mm3']-1),
                'triangle_reduction_fraction':1-len(triangles)/len(baseline_triangles),'source_face_colours':colours,
                'float32_vertex_error_mm':quantization,'origin_mm':origin.tolist(),'bbox_mm':[points.min(axis=0).tolist(),points.max(axis=0).tolist()],
                'visual_collision_same_indexed_geometry':len(collision_triangles)==len(triangles),
                'collision_triangles':len(collision_triangles),'collision_role_binding':role_binding,
                'roles_sha256':sha(roles),'collision_backing_triangles':len(partition['unpainted_backing']),'fitted_curve_surface_substitution':False,'source_unchanged':True,
                'elapsed_seconds':time.perf_counter()-before,
                'producer_sha256':{name:sha(Path(__file__).with_name(name)) for name in ('cad_component.py','cad_component_mesh.py','cad_vector_cache.py','cad_vector_ir.py','cad_collision_roles.py','export_field_package.py','build_vector_component.py')}}
    shutil.copyfile(Path(__file__).resolve().parents[1]/'NOTICE.md',output/'NOTICE.md')
    report['files_sha256']={name:sha(output/name) for name in ('source.step','component.json','visual.glb','collision.glb','geometry.npz','NOTICE.md')}
    with (output/'summary.json').open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:report[k] for k in ('vector_mesh','native_support_validation','triangle_reduction_fraction','volume_relative_difference')},indent=2),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--hierarchy',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--component',default='red-road-surface/body-3789460')
    parser.add_argument('--quality-mm',type=float,default=.1)
    parser.add_argument('--roles',type=Path,default=DEFAULT_ROLES)
    args=parser.parse_args();build(args.source,args.hierarchy,args.out,component_id=args.component,quality_mm=args.quality_mm,roles=args.roles)
