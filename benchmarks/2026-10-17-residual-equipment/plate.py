#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Replace the Tech Core copper plate with projected native profiles extruded 8mm.

This intentionally fills shallow rear relief. Only already-approved circular
front mouths are filled; larger/non-round inner wires remain. All other native
shells retain their current exported attributes. Source CAD is immutable.
"""
import argparse,json
from pathlib import Path
from audit import ROOT,module
from run import join
import numpy as np
from cad_pass_composition import subset
from cad_wall_fill import shape_map
from cad_detail_passes import mesh_native_detail
from cad_profile_prism import projected_prism
from gltf_scene import read_glb,write_glb
from plan_cad_lods import digest
from OCP.TopAbs import TopAbs_WIRE,TopAbs_FACE,TopAbs_SOLID,TopAbs_FORWARD,TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepCheck import BRepCheck_Analyzer


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();cid='technology-core/tool-head';folder=out/cid;composition=module('composition',ROOT/'benchmarks/2026-10-17-composed-pipeline/run.py');pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');source=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step';baseline=ROOT/'out/rmuc2027-composed-pipeline'/cid/'candidate.npz';row=next(r for r in json.loads((out/'summary.json').read_bytes())['components'] if r['id']==cid)
    if digest(source)!=row['source_step_sha256']:raise ValueError('copper source changed')
    doc,reader,faces,shells,owner=composition.native(source);front_index=20;unit=4
    if owner[front_index]!=unit:raise ValueError('plate face ownership changed')
    original=TopoDS.Face(faces.FindKey(front_index));surface=BRepAdaptor_Surface(original);plane=surface.Plane();normal=np.array(plane.Axis().Direction().Coord())*(-1 if original.Orientation()==TopAbs_REVERSED else 1)
    native_mesh=np.load(ROOT/'out/rmuc2027-equipment-pipeline'/cid/'native.npz');original_points=native_mesh['positions_mm'][native_mesh['triangles'][native_mesh['unit_ids']==unit]];projection=original_points@normal;depth=float(np.ptp(projection))
    if abs(depth-8)>.00001 or abs(float(np.array(plane.Location().Coord())@normal)-projection.max())>.00001:raise ValueError('copper profile/thickness no longer matches source')
    mount_path=ROOT/'out/rmuc2027-mounting-native'/cid/'summary.json';mount=json.loads(mount_path.read_bytes())
    if mount['source_step_sha256']!=row['source_step_sha256'] or not any(r['source_native_face_index']==front_index for r in mount['stages']['combined']['proof']['rebuilt_faces']):raise ValueError('front mouth closure not qualified')
    qualified={r['native_face_index']:set(r['native_inner_wire_indices']) for r in mount['bindings']['hole_bindings']}
    admitted={r['source_native_face_index'] for r in mount['stages']['combined']['proof']['rebuilt_faces']}
    native_faces=shape_map(shells.FindKey(unit),TopAbs_FACE);profiles=[];profile_indices=[]
    for i in range(1,native_faces.Extent()+1):
        source_face=TopoDS.Face(native_faces.FindKey(i));adaptor=BRepAdaptor_Surface(source_face)
        from OCP.GeomAbs import GeomAbs_Plane
        if adaptor.GetType()!=GeomAbs_Plane:continue
        if abs(np.dot(adaptor.Plane().Axis().Direction().Coord(),normal))<.999999999:continue
        index=faces.FindIndex(source_face);removed=qualified.get(index,set()) if index in admitted else set()
        face=TopoDS.Face(source_face.Oriented(TopAbs_FORWARD));outer=BRepTools.OuterWire_s(face);maker=BRepBuilderAPI_MakeFace(adaptor.Plane(),outer,True);wires=shape_map(face,TopAbs_WIRE)
        for j in range(1,wires.Extent()+1):
            wire=TopoDS.Wire(wires.FindKey(j))
            if not wire.IsSame(outer) and j not in removed:maker.Add(wire)
        prepared=TopoDS.Face(maker.Face().Oriented(source_face.Orientation()))
        profiles.append(prepared);profile_indices.append(index)
    # Depth-layer projection retains backed regions while preserving real openings.
    front_offset=float(np.array(plane.Location().Coord())@normal)
    prism,union_proof=projected_prism(profiles,normal,front_offset,depth)
    if not BRepCheck_Analyzer(prism).IsValid() or shape_map(prism,TopAbs_SOLID).Extent()!=1:raise ValueError('plate prism is not a valid solid')
    current=np.load(folder/'skin.npz');palette=[v or None for v in current['palette'].tolist()];old_colour=set(map(int,current['material_ids'][current['unit_ids']==unit]))
    if len(old_colour)!=1:raise ValueError('plate source material is not uniform')
    key=next(iter(old_colour));colour=palette[key];p,t,colors,face_ids,proof=mesh_native_detail(prism,[colour]*shape_map(prism,TopAbs_FACE).Extent(),linear_deflection_mm=.1,angular_deflection_rad=.4)
    parts=[]
    for u in np.unique(current['unit_ids']):
        if u==unit:parts.append((p,t,np.full(len(t),key),int(u)))
        else:parts.append((*subset(current,current['unit_ids']==u),int(u)))
    p,t,m,u=join(parts);pipeline.save_mesh(folder,'profile',p,t,m,palette,u)
    export_doc,export_blob=read_glb(folder/'profile.glb')
    for node in export_doc['nodes']:
        if node.get('extras',{}).get('native_shell_index')==unit:node['extras'].update(derived_geometry=True,source_native_shell_binding=unit,geometry_role='native-projected-profile-prism',native_geometry_identity_claim=False)
    write_glb(folder/'profile.glb',export_doc,export_blob)
    result={'id':cid,'source_step_sha256':digest(source),'reference_npz_sha256':digest(baseline),'skin_npz_sha256':digest(folder/'skin.npz'),'mounting_summary_sha256':digest(mount_path),'native_shell_index':unit,'native_front_face_index':front_index,'normal':normal.tolist(),'depth_mm':depth,'projected_native_face_indices':profile_indices,'projection_union':union_proof,'profile_area_mm2':union_proof['profile_area_mm2'],'before_unit_triangles':int((current['unit_ids']==unit).sum()),'after_unit_triangles':int((u==unit).sum()),'component_triangles':len(t),'source_colour':colour,'valid_solid':True,'outputs_sha256':{name:digest(folder/name) for name in ['profile.glb','profile.npz']},'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_profile_prism.py']},'scope':'Derived prism of the coplanar union of all source parallel profiles, extruded to source 8mm depth. Backed recesses close by source projection; through openings survive. Front circular mouths were previously approved. Shallow rear relief intentionally filled; not lossless/backside-equal. All other shells unchanged; original shell index is an override binding, not a source geometry identity claim. No collision/runtime change.'};(folder/'profile.json').write_text(json.dumps(result,indent=2)+'\n');print(result,flush=True)
if __name__=='__main__':main()
