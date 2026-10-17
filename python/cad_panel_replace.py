# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Finite native-solid clipping for explicitly selected panel replacements."""
import math
import numpy as np


def clip_panel_mesh(points_mm,triangles,triangle_srgb,solid,*,selected_srgb=(.2,.2,.2),
                    linear_deflection_mm=.1,angular_deflection_rad=.6):
    """Remove selected material inside a valid finite replacement solid.

    Every potentially intersecting triangle is a native finite face cut by the
    complete solid. Partial faces are remeshed; unselected and disjoint faces
    retain their exact ordered positions and colours. The caller must add the
    replacement's visible skin, qualify its appearance and protect motion.
    This is intentional panel surgery, not inferred hidden-surface deletion.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID
    from cad_wall_fill import shape_map
    from cad_detail_passes import area,mesh_native_detail
    p=np.asarray(points_mm,float);t=np.asarray(triangles);c=np.asarray(triangle_srgb,float);colour=np.asarray(selected_srgb,float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not len(t) or not np.issubdtype(t.dtype,np.integer) or t.min()<0 or t.max()>=len(p) or c.shape!=(len(t),3) or not np.isfinite(c).all() or colour.shape!=(3,):raise ValueError('invalid panel mesh')
    if not all(math.isfinite(v) and v>0 for v in [linear_deflection_mm,angular_deflection_rad]):raise ValueError('invalid panel meshing policy')
    if shape_map(solid,TopAbs_SOLID).Extent()!=1 or not BRepCheck_Analyzer(solid).IsValid():raise ValueError('replacement must be one valid native solid')
    box=Bnd_Box();BRepBndLib.Add_s(solid,box);lo=box.CornerMin();hi=box.CornerMax();bounds=np.array([[lo.X(),lo.Y(),lo.Z()],[hi.X(),hi.Y(),hi.Z()]]);g=p[t];selected=np.all(c==colour,axis=1);near=selected&np.all(g.max(1)>=bounds[0],axis=1)&np.all(g.min(1)<=bounds[1],axis=1);parts=[];colours=[];removed=[];partial=[];untouched=[];unresolved=[]
    for i,tri in enumerate(g):
        if not near[i]:parts.append(tri[None]);colours.append(c[i,None]);untouched.append(i);continue
        original_area=float(np.linalg.norm(np.cross(tri[1]-tri[0],tri[2]-tri[0]))/2)
        if original_area<1e-10:parts.append(tri[None]);colours.append(c[i,None]);untouched.append(i);continue
        wire=BRepBuilderAPI_MakePolygon()
        for point in tri:wire.Add(gp_Pnt(*map(float,point)))
        wire.Close();face=BRepBuilderAPI_MakeFace(wire.Wire()).Face();cut=BRepAlgoAPI_Cut(face,solid);cut.Build()
        if not cut.IsDone() or not BRepCheck_Analyzer(cut.Shape()).IsValid():
            parts.append(tri[None]);colours.append(c[i,None]);untouched.append(i);unresolved.append(i);continue
        result=cut.Shape();outside_area=area(result)
        if abs(outside_area-original_area)<=max(1e-7,original_area*1e-9):parts.append(tri[None]);colours.append(c[i,None]);untouched.append(i);continue
        if outside_area<=1e-7:removed.append(i);continue
        face_count=shape_map(result,TopAbs_FACE).Extent()
        if not face_count:raise ValueError('remaining triangle area has no face')
        try:pp,tt,_,_,proof=mesh_native_detail(result,[','.join(map(str,c[i]))]*face_count,linear_deflection_mm=linear_deflection_mm,angular_deflection_rad=angular_deflection_rad)
        except ValueError:
            parts.append(tri[None]);colours.append(c[i,None]);untouched.append(i);unresolved.append(i);continue
        parts.append(pp[tt]);colours.append(np.tile(c[i],(len(tt),1)));partial.append({'input_triangle_index':i,'before_area_mm2':original_area,'remaining_area_mm2':outside_area,'after_triangles':len(tt)})
    output=np.concatenate(parts) if parts else np.empty((0,3,3));return output.reshape(-1,3),np.arange(len(output)*3).reshape(-1,3),np.concatenate(colours) if colours else np.empty((0,3)),{'pass':'native-finite-panel-clip-v1','before_triangles':len(t),'after_triangles':len(output),'removed_input_triangle_indices':removed,'partial_triangles':partial,'untouched_input_triangle_indices':untouched,'retained_unresolved_triangle_indices':unresolved,'selected_srgb':colour.tolist(),'valid_replacement_solid':True,'scope':'Native finite surface cuts against an explicit replacement solid; unselected triangles retain positions. Source STEP and inferred visibility ownership unchanged.'}
