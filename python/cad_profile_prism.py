# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Extrude a source-owned union of parallel profiles into a visual plate envelope.

Backed recesses intentionally become solid; openings through every depth layer
remain. This is not a lossless solid edit. Callers bind faces/material/motion and
any already approved mouth closures before passing profiles to this operation.
"""
import math
import numpy as np
from cad_wall_fill import shape_map


def projected_prism(faces, normal, front_offset_mm, depth_mm, *,
                    maximum_lateral_shift_mm=.001, fusion_tolerance_mm=.001):
    """Normalize parallel native profiles, unite them and extrude to source depth.

    Complete native wires/curves survive projection, including inner loops; this
    function never fills a hole based on size. Source planes must lie inside the
    requested depth band. Tiny frame rotations have a checked lateral allowance.
    The result is one valid solid with a complete source-profile proof; source
    objects stay unchanged. The finite depth is a deliberate relief-fill policy.
    """
    from OCP.TopAbs import TopAbs_FACE,TopAbs_VERTEX,TopAbs_REVERSED,TopAbs_SOLID
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.gp import gp_Vec,gp_Ax3,gp_Pnt,gp_Dir,gp_Trsf
    from cad_detail_passes import area
    n=np.asarray(normal,float)
    if not faces or n.shape!=(3,) or not np.isfinite(n).all() or np.linalg.norm(n)<1e-12 or not math.isfinite(front_offset_mm) or not all(math.isfinite(v) and v>0 for v in [depth_mm,maximum_lateral_shift_mm,fusion_tolerance_mm]):raise ValueError('invalid profile-prism policy')
    n=n/np.linalg.norm(n);prepared=[];records=[];maximum_lateral=0
    for original in faces:
        face=TopoDS.Face(original);surface=BRepAdaptor_Surface(face)
        if surface.GetType()!=GeomAbs_Plane:raise ValueError('profile is not planar')
        plane=surface.Plane();position=plane.Position();location=np.array(position.Location().Coord());axis=np.array(position.Direction().Coord())
        if abs(axis@n)<.999999999:raise ValueError('profile plane is not parallel')
        offset=float(location@n)
        if offset>front_offset_mm+.001 or offset<front_offset_mm-depth_mm-.001:raise ValueError('profile outside the authorized depth band')
        aligned=n*(1 if axis@n>=0 else -1);x=np.array(position.XDirection().Coord());x-=aligned*(x@aligned);x/=np.linalg.norm(x);target_point=location+n*(front_offset_mm-offset)
        target=gp_Ax3(gp_Pnt(*map(float,target_point)),gp_Dir(*map(float,aligned)),gp_Dir(*map(float,x)));transform=gp_Trsf();transform.SetDisplacement(position,target)
        vertices=shape_map(face,TopAbs_VERTEX);lateral=0
        for i in range(1,vertices.Extent()+1):
            point=BRep_Tool.Pnt_s(TopoDS.Vertex(vertices.FindKey(i)));delta=np.array(point.Transformed(transform).Coord())-np.array(point.Coord());lateral=max(lateral,float(np.linalg.norm(delta-n*(delta@n))))
        if lateral>maximum_lateral_shift_mm:raise ValueError('profile normalization exceeds the lateral allowance')
        result=TopoDS.Face(BRepBuilderAPI_Transform(face,transform,True).Shape());axis=np.array(BRepAdaptor_Surface(result).Plane().Axis().Direction().Coord())*(-1 if result.Orientation()==TopAbs_REVERSED else 1)
        if axis@n<0:result=TopoDS.Face(result.Reversed())
        prepared.append(result);maximum_lateral=max(maximum_lateral,lateral);records.append({'source_offset_mm':offset,'source_area_mm2':area(face),'maximum_lateral_shift_mm':lateral})
    cap=prepared[0]
    for face in prepared[1:]:
        op=BRepAlgoAPI_Fuse(cap,face);op.SetFuzzyValue(fusion_tolerance_mm);op.SetNonDestructive(True);op.Build()
        if not op.IsDone():raise ValueError('projected profile union failed')
        cap=op.Shape()
    unify=ShapeUpgrade_UnifySameDomain(cap,True,True,False);unify.SetLinearTolerance(fusion_tolerance_mm);unify.SetAngularTolerance(1e-6);unify.Build();cap=unify.Shape();profiles=shape_map(cap,TopAbs_FACE)
    if profiles.Extent()!=1 or not BRepCheck_Analyzer(cap).IsValid():raise ValueError('profile union is not one valid connected face')
    cap=TopoDS.Face(profiles.FindKey(1));solid=BRepPrimAPI_MakePrism(cap,gp_Vec(*map(float,-n*depth_mm))).Shape()
    if shape_map(solid,TopAbs_SOLID).Extent()!=1 or not BRepCheck_Analyzer(solid).IsValid():raise ValueError('profile prism is not one valid solid')
    return solid,{'pass':'native-projected-profile-prism-v1','profiles':records,'front_normal':n.tolist(),'front_offset_mm':front_offset_mm,'depth_mm':depth_mm,'profile_area_mm2':area(cap),'maximum_lateral_shift_mm':maximum_lateral,'lateral_allowance_mm':maximum_lateral_shift_mm,'fusion_tolerance_mm':fusion_tolerance_mm,'valid_solid':True,'scope':'Same-material source profiles projected and united before extrusion. Backed recesses filled, common through-openings retained. Intentional depth-envelope approximation; not lossless, collision or source-identity geometry.'}
