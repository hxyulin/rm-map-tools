#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Close the reviewed crossbar mounting row from pinned native source topology."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from validate_parts import read_part
from plan_cad_lods import digest
from cad_wall_fill import shape_map
from cad_surface_lods import close_selected_axial_bores,close_bore_surfaces,material_lod,cap_selected_recess_mesh
from cad_detail_passes import mesh_native_detail
from export_field_package import GlbWriter
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID,TopAbs_WIRE,TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=ROOT/'out/rmuc2027-base-structure-audit');ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();policy_path=ROOT/'rules/base-mounting-row-rmuc2027.json';policy=json.loads(policy_path.read_bytes());audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());src=a.source/'source.step'
    if a.out.exists():raise FileExistsError(a.out)
    if digest(src)!=policy['component_step_sha256']:raise ValueError('source mismatch')
    doc,reader,error=read_part(str(src))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);solids=shape_map(root,TopAbs_SOLID);source=policy['source_unit_id'];index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source);indices={f['native_face_index'] for f in audit['faces'] if f['unit']==index};by_index={f['native_face_index']:f for f in audit['faces']}
    for j in range(1,solids.Extent()+1):
        shape=solids.FindKey(j);local=shape_map(shape,TopAbs_FACE)
        if {faces.FindIndex(local.FindKey(k)) for k in range(1,local.Extent()+1)}==indices:break
    else:raise ValueError('unit missing')
    colors=[by_index[faces.FindIndex(local.FindKey(j))]['source_colour'] for j in range(1,local.Extent()+1)];source_ids=[by_index[faces.FindIndex(local.FindKey(j))]['source_face_id'] for j in range(1,local.Extent()+1)];entry=source_ids.index(policy['entry_source_face_id'])+1
    closed,map1,proof=close_selected_axial_bores(shape,entry_face_index=entry,entry_wire_indices=policy['entry_wire_indices'],maximum_gap_mm=policy['strict_maximum_gap_mm'])
    if len(proof['closed_bores'])!=policy['expected_bores']:raise ValueError('mount count mismatch')
    for bore in proof['closed_bores']:
        if not np.allclose(bore['radii_mm'],policy['expected_radii_mm'],rtol=0,atol=1e-5):raise ValueError('unexpected bore radii')
    # The earlier straight pass already closed the 10 small throats. Full stepped
    # closure subsumes those operations and leaves 56 other straight bores.
    previous=json.loads((a.source/'trial-summary.json').read_bytes());prior=next(t for t in previous['trials'] if t['source_unit_id']==source)['native_closure'];removed=set(proof['removed_wall_and_shoulder_faces']);subsumed=[b for b in prior['closed_bores'] if set(b['wall_face_indices'])<=removed]
    if len(subsumed)!=10:raise ValueError('previous throat-closure overlap changed')
    derived,map2,straight=close_bore_surfaces(closed,maximum_gap_mm=policy['strict_maximum_gap_mm']);mapping=[map1[i-1] for i in map2]
    if len(straight['closed_bores'])!=56:raise ValueError('remaining straight-bore selection changed')
    retained_old_walls={i for b in prior['closed_bores'] for i in b['wall_face_indices']}-removed
    new_straight_walls={map1[i-1] for b in straight['closed_bores'] for i in b['wall_face_indices']}
    if retained_old_walls!=new_straight_walls:raise ValueError('prior straight-bore wall coverage changed')
    proof['input_face_source_ids']=source_ids;proof['previous_throat_closures_subsumed']=len(subsumed)
    p,t,keys,face_ids,mesh=mesh_native_detail(derived,[colors[i-1] for i in mapping],linear_deflection_mm=policy['linear_deflection_mm'],angular_deflection_rad=policy['angular_deflection_rad']);palette,mat=np.unique(np.array([key or '0.6275,0.6275,0.6275' for key in keys]),return_inverse=True)
    p,t,m,lod=material_lod(p,t,mat,error_mm=policy['visual_error_mm'],sampled_limit_mm=policy['visual_sampled_limit_mm'],sample_count=8192);rgb=np.array([list(map(float,key.split(','))) for key in palette])[m]
    remesh_count=len(t)
    mouth_features=[];entry_wires=shape_map(local.FindKey(entry),TopAbs_WIRE)
    for wire in policy['mouth_only_entry_wire_indices']:
        ee=shape_map(entry_wires.FindKey(wire),TopAbs_EDGE);circle=BRepAdaptor_Curve(TopoDS.Edge(ee.FindKey(1))).Circle();normal=circle.Axis().Direction();origin=circle.Location();axis=np.array([normal.X(),normal.Y(),normal.Z()]);origin=np.array([origin.X(),origin.Y(),origin.Z()]);mouth=float(axis@origin)
        if abs(circle.Radius()-policy['entry_radius_mm'])>1e-5:raise ValueError('unexpected end-mouth radius')
        mouth_features.append({'axis_direction':axis.tolist(),'axis_anchor_mm':(origin-axis*mouth).tolist(),'end_parameters_mm':[mouth-4,mouth],'radii_mm':[circle.Radius()],'mouth_parameter_mm':mouth,'retain_interior':True,'source_entry_wire_index':wire})
    proof['mouth_only_features']=mouth_features
    reference_path=a.source/'4268930/trial.npz';old_record=next(t for t in previous['trials'] if t['source_unit_id']==source)
    if digest(reference_path)!=old_record['geometry_sha256']:raise ValueError('approved crossbar changed')
    reference=np.load(reference_path);p,t,rgb,local_proof=cap_selected_recess_mesh(reference['positions_mm'],reference['triangles'],reference['triangle_srgb'],proof['closed_bores']+mouth_features,radial_margin_mm=1,plane_tolerance_mm=.001)
    retained=local_proof['retained_original_triangle_indices'];old_tri=reference['positions_mm'][reference['triangles'][retained]]
    if not np.array_equal(p[t[:len(retained)]],old_tri) or not np.array_equal(rgb[:len(retained)],reference['triangle_srgb'][retained]):raise ValueError('untouched crossbar triangles changed')
    if len(t)>=len(reference['triangles']):raise ValueError('local patch does not save triangles')
    a.out.mkdir(parents=True);np.savez(a.out/'geometry.npz',positions_mm=p,triangles=t,triangle_srgb=rgb,unit_ids=np.full(len(t),index,dtype=np.uint32),source_face_ids=np.zeros(len(t),dtype=np.uint32));writer=GlbWriter('base/crossbar-mounting-row',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; derived selected mounting-row closure'});writer.add_node('source-unit-'+str(source),p/1000,t,[','.join(map(str,c)) for c in rgb],extras={'source_unit_id':source,'inspection_only':True});writer.write(a.out/'visual.glb')
    old=json.loads((a.source/'trial-summary.json').read_bytes());before=next(t['after_triangles'] for t in old['trials'] if t['source_unit_id']==source);report={'component_step_sha256':digest(src),'policy_sha256':digest(policy_path),'source_unit_id':source,'entry_source_face_id':policy['entry_source_face_id'],'original_local_face_source_ids':source_ids,'mounting_row':proof,'straight_bores':straight,'native_mesh':mesh,'rejected_whole_remesh_triangles':remesh_count,'rejected_whole_remesh_lod':lod,'local_mesh':local_proof,'reference_geometry_sha256':digest(reference_path),'previous_crossbar_triangles':before,'crossbar_triangles':len(t),'previous_base_triangles':136982-39790+before,'base_triangles':136982-39790+len(t),'collision_triangles_unchanged':16857,'geometry_sha256':digest(a.out/'geometry.npz'),'visual_sha256':digest(a.out/'visual.glb'),'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_surface_lods.py']},'scope':policy['scope']};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print('crossbar',before,'->',len(t),'Base',report['base_triangles'],flush=True)
if __name__=='__main__':main()
