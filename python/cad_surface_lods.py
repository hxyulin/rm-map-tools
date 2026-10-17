# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Separate visual relief, protected appearance and source-profile collision LOD.

These are approximate derived outputs. Callers explicitly select source units,
protect detector/light faces, pin checksums and review every replacement. No
policy here infers that an unobserved surface is disposable.
"""
import math
import numpy as np


def material_lod(points_mm, triangles, material_ids, *, error_mm,
                 protected_material_ids=(), sample_count=2048, sampled_limit_mm=None,
                 material_policies=None):
    """Reduce each material region with its open border locked.

    Protected regions retain ordered source triangles in float64. Other regions
    use the existing component-retaining meshoptimizer backend, rebased around
    their local origin before float32 conversion. Two-sided deterministic sample
    checks supplement its error metric; neither is a continuous error proof.
    Optional per-material policies override the metric and sampled limit (for
    example stricter LEDs). Returns positions, indices, per-triangle material ids
    and a measurement ledger.
    """
    from simplify_package import simplify_mesh
    from mesh_quality import deviation
    p=np.asarray(points_mm,dtype=np.float64);t=np.asarray(triangles);m=np.asarray(material_ids)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or m.shape!=(len(t),):
        raise ValueError('invalid material mesh')
    if not math.isfinite(error_mm) or error_mm<=0 or type(sample_count) is not int or not 96<=sample_count<=16384:
        raise ValueError('invalid LOD policy')
    limit=error_mm*2 if sampled_limit_mm is None else sampled_limit_mm
    if not math.isfinite(limit) or limit<=0:raise ValueError('invalid sampled deviation limit')
    protected=set(protected_material_ids);pp=[];tt=[];mm=[];records=[];offset=0
    for key in np.unique(m):
        old=t[m==key];used,inv=np.unique(old,return_inverse=True);before=p[used];old=inv.reshape(-1,3)
        if key in protected:
            out=before;faces=old;record={'protected':True,'byte_exact_triangle_positions':True}
        else:
            origin=(before.min(0)+before.max(0))/2
            settings=(material_policies or {}).get(int(key),{})
            region_error=settings.get('error_mm',error_mm);region_limit=settings.get('sampled_limit_mm',limit)
            if not all(math.isfinite(x) and x>0 for x in (region_error,region_limit)):raise ValueError('invalid material LOD override')
            trials=[]
            for refinement in range(5):
                requested=region_error/2**refinement
                local,faces,error=simplify_mesh(before-origin,old,requested,lock_borders=True);out=local.astype(float)+origin
                sampled=deviation(before,old,out,faces,count=sample_count)
                trials.append({'requested_error_mm':requested,'sampled_max_mm':sampled['max'],'triangles':len(faces)})
                if sampled['max']<=region_limit:break
            else:raise ValueError(f'sampled deviation {sampled["max"]} mm exceeds {region_limit} mm after refinement')
            record={'protected':False,'meshoptimizer_error_mm':error,'refinement_trials':trials,'sampled_deviation_mm':sampled,'sampled_limit_mm':region_limit}
        record.update(material_id=int(key),before_triangles=len(old),after_triangles=len(faces));records.append(record)
        pp.append(out);tt.append(faces+offset);offset+=len(out);mm.extend([key]*len(faces))
    return np.concatenate(pp),np.concatenate(tt),np.asarray(mm,dtype=m.dtype),{
        'pass':'material-region-lod-v1','requested_error_mm':error_mm,'locked_material_borders':True,
        'regions':records,'scope':'Sample-checked approximate mesh LOD; original CAD unchanged. Source-face ownership is regional, not invented for new triangles.'}


def profile_prism(face, *, depth_mm, maximum_filled_hole_area_mm2=0, maximum_gap_mm=None):
    """Extrude an explicit native planar outline into a closed collision plate.

    Native outer wire is retained. Inner loops larger than the caller's area
    threshold remain open; smaller loops are intentionally capped. When supplied,
    maximum_gap_mm selects strict native width instead of area. Signed depth
    follows the native plane normal, independent of source face orientation.
    This replaces the selected member: ribs, posts and relief are not retained.
    It is not an enclosure or a conservative hull guarantee.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.TopAbs import TopAbs_WIRE,TopAbs_SOLID,TopAbs_FORWARD
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Vec
    from cad_wall_fill import shape_map,volume
    from cad_detail_passes import area
    if not math.isfinite(depth_mm) or abs(depth_mm)<1e-6 or not math.isfinite(maximum_filled_hole_area_mm2) or maximum_filled_hole_area_mm2<0:
        raise ValueError('invalid profile extrusion policy')
    if maximum_gap_mm is not None and (not math.isfinite(maximum_gap_mm) or maximum_gap_mm<=0):raise ValueError('invalid strict gap policy')
    face=TopoDS.Face(face.Oriented(TopAbs_FORWARD));surface=BRepAdaptor_Surface(face)
    if surface.GetType()!=GeomAbs_Plane:raise ValueError('profile requires a native planar face')
    plane=surface.Plane();outer=BRepTools.OuterWire_s(face);cap=BRepBuilderAPI_MakeFace(plane,outer,True);wires=shape_map(face,TopAbs_WIRE);filled=[];kept=[];width_records=[]
    for i in range(1,wires.Extent()+1):
        wire=TopoDS.Wire(wires.FindKey(i))
        if wire.IsSame(outer):continue
        loop_area=area(BRepBuilderAPI_MakeFace(plane,wire,True).Face())
        width=wire_width_bound_mm(face,wire) if maximum_gap_mm is not None else None
        close=width<maximum_gap_mm if maximum_gap_mm is not None else loop_area<=maximum_filled_hole_area_mm2
        width_records.append({'area_mm2':loop_area,'native_width_upper_bound_mm':width,'closed':close})
        if close:filled.append(loop_area)
        else:cap.Add(wire);kept.append(loop_area)
    planar=cap.Face()
    if not BRepCheck_Analyzer(planar).IsValid():raise ValueError('invalid retained native profile')
    result=BRepPrimAPI_MakePrism(planar,gp_Vec(plane.Axis().Direction())*depth_mm).Shape()
    if not BRepCheck_Analyzer(result).IsValid() or shape_map(result,TopAbs_SOLID).Extent()!=1:raise ValueError('profile did not produce one valid solid')
    expected=area(planar)*abs(depth_mm);measured=abs(volume(result))
    if abs(expected-measured)>max(1e-5,expected*1e-9):raise ValueError('extrusion volume accounting failed')
    return result,{'pass':'source-profile-collision-v1','signed_depth_mm':depth_mm,'outer_wire_unchanged':True,
                   'filled_hole_areas_mm2':filled,'retained_hole_areas_mm2':kept,'maximum_filled_hole_area_mm2':maximum_filled_hole_area_mm2,
                   'strict_maximum_gap_mm':maximum_gap_mm,'opening_widths':width_records,'valid_single_solid':True,'volume_mm3':measured,
                   'scope':'Explicit replacement plate, not a source-material union or containment guarantee. Small holes and relief intentionally omitted.'}


def wire_width_bound_mm(face, wire):
    """Bound a finite planar opening's width using native oriented boxes.

    Candidate calipers follow the plane axes and native straight edges. Each
    tested box includes complete native curves without using triangulation.
    Its shorter side is an upper bound on an opening's minimum caliper width,
    not its inscribed diameter. Failure to find a narrow box keeps the opening.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Plane,GeomAbs_Line
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Ax3,gp_Dir,gp_Trsf
    from cad_wall_fill import shape_map
    surface=BRepAdaptor_Surface(TopoDS.Face(face))
    if surface.GetType()!=GeomAbs_Plane:raise ValueError('opening width requires a native plane')
    plane=surface.Plane();directions=[plane.Position().XDirection()];edges=shape_map(wire,TopAbs_EDGE)
    for i in range(1,edges.Extent()+1):
        curve=BRepAdaptor_Curve(TopoDS.Edge(edges.FindKey(i)))
        if curve.GetType()==GeomAbs_Line:directions.append(curve.Line().Direction())
    widths=[];seen=set();normal=plane.Axis().Direction()
    for direction in directions:
        # Sign canonicalization retains distinct mirrored/slanted calipers.
        xyz=np.array([direction.X(),direction.Y(),direction.Z()]);xyz*=1 if xyz[np.argmax(abs(xyz))]>=0 else -1;key=tuple(np.round(xyz,10))
        if key in seen:continue
        seen.add(key);transform=gp_Trsf();transform.SetTransformation(gp_Ax3(plane.Location(),normal,gp_Dir(*xyz)))
        local=BRepBuilderAPI_Transform(wire,transform,True).Shape();box=Bnd_Box();BRepBndLib.AddOptimal_s(local,box,False,True);low=box.CornerMin();high=box.CornerMax();widths.append(min(high.X()-low.X(),high.Y()-low.Y()))
    if not widths or not all(math.isfinite(x) and x>=0 for x in widths):raise ValueError('invalid native opening extent')
    return min(widths)


def close_bore_surfaces(source, *, maximum_gap_mm):
    """Cap complete native cylindrical bores narrower than an explicit limit.

    This surface pass preserves other native faces, replaces only the two end
    planes' affected inner loops, and removes each closed bore's cylindrical
    walls. It needs no Boolean on a complex near-coincident solid. The output
    is a derived surface compound; no healed/watertight solid claim is made.
    Independently moving members must be passed separately by the caller.
    """
    from cad_detail_passes import small_bore_groups,compound
    from cad_wall_fill import shape_map
    from OCP.TopAbs import TopAbs_FACE,TopAbs_EDGE,TopAbs_WIRE,TopAbs_FORWARD
    from OCP.TopoDS import TopoDS
    from OCP.BRepTools import BRepTools
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepCheck import BRepCheck_Analyzer
    if not math.isfinite(maximum_gap_mm) or maximum_gap_mm<=0:raise ValueError('invalid gap limit')
    faces=shape_map(source,TopAbs_FACE);groups=small_bore_groups(source,maximum_radius_mm=maximum_gap_mm/2,maximum_depth_mm=10000)
    groups=[g for g in groups if 2*g['radius_mm']<maximum_gap_mm-1e-6]
    removed=set();selected={};accepted=[]
    for g in groups:
        mapped=[];end_widths=[]
        for index in g['adjacent_plane_indices']:
            face=TopoDS.Face(faces.FindKey(index).Oriented(TopAbs_FORWARD));outer=BRepTools.OuterWire_s(face);wires=shape_map(face,TopAbs_WIRE);wall_edges=shape_map(compound(faces.FindKey(i) for i in g['face_indices']),TopAbs_EDGE);matches=[]
            for j in range(1,wires.Extent()+1):
                wire=TopoDS.Wire(wires.FindKey(j));edges=shape_map(wire,TopAbs_EDGE)
                if not wire.IsSame(outer) and all(wall_edges.Contains(edges.FindKey(k)) for k in range(1,edges.Extent()+1)):matches.append(j)
            if len(matches)!=1:raise ValueError('bore does not match exactly one finite inner wire at each end')
            end_widths.append(wire_width_bound_mm(face,TopoDS.Wire(wires.FindKey(matches[0]))))
            mapped.append((index,matches[0]))
        if any(width>=maximum_gap_mm for width in end_widths):continue
        removed.update(g['face_indices'])
        for index,wire_index in mapped:selected.setdefault(index,set()).add(wire_index)
        accepted.append({'end_opening_width_bounds_mm':end_widths,'diameter_mm':2*g['radius_mm'],'depth_mm':g['depth_mm'],'wall_face_indices':g['face_indices'],'end_plane_indices':g['adjacent_plane_indices']})
    result=[];source_indices=[]
    for i in range(1,faces.Extent()+1):
        if i in removed:continue
        face=TopoDS.Face(faces.FindKey(i))
        if i in selected:
            original_orientation=face.Orientation();forward=TopoDS.Face(face.Oriented(TopAbs_FORWARD));plane=BRepAdaptor_Surface(forward).Plane();outer=BRepTools.OuterWire_s(forward);builder=BRepBuilderAPI_MakeFace(plane,outer,True);wires=shape_map(forward,TopAbs_WIRE)
            for j in range(1,wires.Extent()+1):
                wire=TopoDS.Wire(wires.FindKey(j))
                if not wire.IsSame(outer) and j not in selected[i]:builder.Add(wire)
            face=builder.Face()
            if not BRepCheck_Analyzer(face).IsValid():raise ValueError('capped native plane is invalid')
            face=TopoDS.Face(face.Oriented(original_orientation))
        result.append(face);source_indices.append(i)
    return compound(result),source_indices,{'pass':'native-bore-surface-closure-v1','strict_maximum_gap_mm':maximum_gap_mm,'closed_bores':accepted,'removed_wall_faces':len(removed),'rebuilt_end_planes':sorted(selected),'source_faces':faces.Extent(),'result_faces':len(result),'scope':'Only complete circular bores closed; other faces retained by identity. Surface compound, not a solid-healing proof or cross-member fusion.'}
