# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Native-profile flat visual backs for explicitly selected equipment panels."""
import math
import numpy as np


def flat_back(faces, front, rear_offset_mm, *, maximum_gap_mm=17):
    """Unite selected parallel native profiles on one rear plane.

    Retains each native outer wire and inner openings at least ``maximum_gap_mm``
    wide; smaller bores are intentionally filled. Moves profiles only along the
    front axis, then unions and unifies the coplanar patches. The resulting face
    skin has no internal hardware or thickness and is not a collision solid.
    Callers retain source-face bindings separately: this is derived geometry.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace,BRepBuilderAPI_Transform
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopAbs import TopAbs_WIRE,TopAbs_FACE,TopAbs_FORWARD
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Trsf,gp_Vec
    from cad_surface_lods import wire_width_bound_mm
    from cad_wall_fill import shape_map
    from cad_detail_passes import area
    f=np.array(front,dtype=float,copy=True)
    if not faces or f.shape!=(3,) or not np.isfinite(f).all() or np.linalg.norm(f)<1e-12 or not math.isfinite(rear_offset_mm) or not math.isfinite(maximum_gap_mm) or maximum_gap_mm<=0:raise ValueError('invalid flat back policy')
    f/=np.linalg.norm(f);result=None;records=[]
    for original in faces:
        face=TopoDS.Face(original.Oriented(TopAbs_FORWARD));surface=BRepAdaptor_Surface(face)
        if surface.GetType()!=GeomAbs_Plane:raise ValueError('rear profile is not planar')
        plane=surface.Plane();axis=plane.Axis().Direction();normal=np.array([axis.X(),axis.Y(),axis.Z()])
        if abs(normal@f)<1-1e-9:raise ValueError('rear profile is not parallel to front')
        maker=BRepBuilderAPI_MakeFace(plane,BRepTools.OuterWire_s(face),True);wires=shape_map(face,TopAbs_WIRE);outer=BRepTools.OuterWire_s(face);holes=[]
        for i in range(1,wires.Extent()+1):
            wire=TopoDS.Wire(wires.FindKey(i))
            if wire.IsSame(outer):continue
            width=wire_width_bound_mm(face,wire);filled=width<maximum_gap_mm;holes.append({'width_upper_bound_mm':width,'filled':filled})
            if not filled:maker.Add(wire)
        cap=maker.Face();point=plane.Location();offset=np.array([point.X(),point.Y(),point.Z()])@f;trsf=gp_Trsf();trsf.SetTranslation(gp_Vec(*map(float,f*(rear_offset_mm-offset))));cap=BRepBuilderAPI_Transform(cap,trsf,True).Shape()
        if not BRepCheck_Analyzer(cap).IsValid():raise ValueError('invalid flat cap profile')
        records.append({'original_area_mm2':area(face),'cap_profile_area_mm2':area(cap),'source_offset_mm':float(offset),'translation_mm':float(rear_offset_mm-offset),'holes':holes})
        if result is None:result=cap
        else:
            operation=BRepAlgoAPI_Fuse(result,cap);operation.Build()
            if not operation.IsDone():raise ValueError('coplanar profile union failed')
            result=operation.Shape()
    unify=ShapeUpgrade_UnifySameDomain(result,True,True,False);unify.Build();result=unify.Shape()
    if not BRepCheck_Analyzer(result).IsValid() or not shape_map(result,TopAbs_FACE).Extent():raise ValueError('invalid united flat back')
    faces_map=shape_map(result,TopAbs_FACE)
    # Give the derived panel an explicit outward rear orientation.
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    compound=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(compound)
    for i in range(1,faces_map.Extent()+1):
        face=TopoDS.Face(faces_map.FindKey(i));normal=BRepAdaptor_Surface(face).Plane().Axis().Direction();n=np.array([normal.X(),normal.Y(),normal.Z()])
        from OCP.TopAbs import TopAbs_REVERSED
        outward=n*(-1 if face.Orientation()==TopAbs_REVERSED else 1)
        if outward@f>0:face=TopoDS.Face(face.Reversed())
        builder.Add(compound,face)
    return compound,{'pass':'native-profile-flat-back-v1','rear_offset_mm':rear_offset_mm,'front_direction':f.tolist(),'maximum_filled_gap_mm':maximum_gap_mm,'profiles':records,'result_faces':faces_map.Extent(),'result_area_mm2':area(compound),'scope':'Derived coplanar union of authored outer profiles; small holes filled, large cutouts kept. No thickness, hardware, collision or source-face identity claim.'}
