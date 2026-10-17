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


def close_selected_axial_bores(source, *, entry_face_index, entry_wire_indices,
                               maximum_gap_mm):
    """Close explicitly selected complete coaxial cylindrical/stepped/countersunk bores.

    Indices refer to the caller-pinned native face/wire inventory, starting at one.
    Every cylindrical wall must face inward and cover full turns collectively.
    Intermediate shoulders must be complete coaxial annuli. Exactly two exterior
    planar mouths are required, both strictly below the width limit. Blind,
    intersecting and unresolved channels reject the entire selection.
    Other faces retain native identity; returned indices carry their original
    appearance. The result is a surface compound, not a healed solid guarantee.
    """
    from cad_detail_passes import compound
    from cad_wall_fill import shape_map
    from OCP.TopAbs import TopAbs_FACE,TopAbs_EDGE,TopAbs_WIRE,TopAbs_FORWARD,TopAbs_REVERSED
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Plane,GeomAbs_Cylinder,GeomAbs_Cone,GeomAbs_Circle,GeomAbs_Line
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepCheck import BRepCheck_Analyzer
    if not math.isfinite(maximum_gap_mm) or maximum_gap_mm<=0:raise ValueError('invalid axial bore width policy')
    if type(entry_face_index) is not int or entry_face_index<1:raise ValueError('invalid entry face index')
    selected=list(entry_wire_indices)
    if not selected or any(type(i) is not int or i<1 for i in selected) or len(set(selected))!=len(selected):raise ValueError('invalid entry wire selection')
    faces=shape_map(source,TopAbs_FACE);edges=shape_map(source,TopAbs_EDGE)
    if entry_face_index>faces.Extent():raise ValueError('entry face outside source inventory')
    entry=TopoDS.Face(faces.FindKey(entry_face_index));surface=BRepAdaptor_Surface(entry)
    if surface.GetType()!=GeomAbs_Plane:raise ValueError('entry mouth must be planar')
    wires=shape_map(entry,TopAbs_WIRE);outer=BRepTools.OuterWire_s(entry);owners={}
    for i in range(1,faces.Extent()+1):
        ee=shape_map(faces.FindKey(i),TopAbs_EDGE)
        for j in range(1,ee.Extent()+1):owners.setdefault(edges.FindIndex(ee.FindKey(j)),set()).add(i)
    xyz=lambda v:np.array([v.X(),v.Y(),v.Z()])
    removed=set();rebuild={};proofs=[]
    for selected_wire in selected:
        if selected_wire>wires.Extent() or wires.FindKey(selected_wire).IsSame(outer):raise ValueError('entry wire is not an inner loop')
        mouth=TopoDS.Wire(wires.FindKey(selected_wire));ee=shape_map(mouth,TopAbs_EDGE);first=BRepAdaptor_Curve(TopoDS.Edge(ee.FindKey(1)))
        if first.GetType()!=GeomAbs_Circle:raise ValueError('selected mouth is not circular')
        circle=first.Circle();axis=xyz(circle.Axis().Direction());anchor=xyz(circle.Location());anchor-=axis*np.dot(anchor,axis)
        def coaxial(ax):
            direction=xyz(ax.Direction());origin=xyz(ax.Location())
            return abs(abs(np.dot(axis,direction))-1)<1e-8 and np.linalg.norm(origin-axis*np.dot(origin,axis)-anchor)<1e-5
        def ring(wire, enforce_limit=True):
            local=shape_map(wire,TopAbs_EDGE);radii=[];span=0.
            for k in range(1,local.Extent()+1):
                curve=BRepAdaptor_Curve(TopoDS.Edge(local.FindKey(k)))
                if curve.GetType()!=GeomAbs_Circle or not coaxial(curve.Circle().Axis()):raise ValueError('noncoaxial or noncircular channel boundary')
                radii.append(curve.Circle().Radius());span+=abs(curve.LastParameter()-curve.FirstParameter())
            if max(radii)-min(radii)>1e-6 or abs(span-2*math.pi)>1e-5:raise ValueError('incomplete circular boundary')
            if enforce_limit and 2*max(radii)>=maximum_gap_mm-1e-6:raise ValueError('bore mouth or shoulder reaches width limit')
            return radii[0]
        ring(mouth)
        if abs(abs(np.dot(axis,xyz(surface.Plane().Axis().Direction())))-1)>1e-8:raise ValueError('entry plane not perpendicular to bore')
        queue=[]
        for k in range(1,ee.Extent()+1):queue.extend(owners[edges.FindIndex(ee.FindKey(k))]-{entry_face_index})
        if not queue:raise ValueError('entry has no channel walls')
        visited=set();ends={(entry_face_index,selected_wire)};walls=[];shoulders=[];turns={}
        while queue:
            i=queue.pop()
            if i in visited:continue
            visited.add(i);face=TopoDS.Face(faces.FindKey(i));s=BRepAdaptor_Surface(face)
            if s.GetType() in (GeomAbs_Cylinder,GeomAbs_Cone):
                cylinder=s.Cylinder() if s.GetType()==GeomAbs_Cylinder else s.Cone()
                if not coaxial(cylinder.Axis()) or face.Orientation()!=TopAbs_REVERSED:raise ValueError(f'unsupported axial wall at {i}: coaxial={coaxial(cylinder.Axis())}, orientation={face.Orientation()}')
                uv=BRepTools.UVBounds_s(face);direction=xyz(cylinder.Axis().Direction());origin=xyz(cylinder.Axis().Location())
                if s.GetType()==GeomAbs_Cylinder:
                    radius=cylinder.Radius();axial_v=uv[2:];kind='cylinder'
                else:
                    radii=[cylinder.RefRadius()+v*math.sin(cylinder.SemiAngle()) for v in uv[2:]]
                    if min(radii)<=1e-6:raise ValueError('conical channel reaches an apex')
                    radius=max(radii);axial_v=[v*math.cos(cylinder.SemiAngle()) for v in uv[2:]];kind='cone'
                if 2*radius>=maximum_gap_mm-1e-6:raise ValueError('oversized axial wall')
                zz=sorted(float(np.dot(axis,origin+direction*v)) for v in axial_v);key=(round(radius,5),round(zz[0],5),round(zz[1],5),kind);turns[key]=turns.get(key,0)+abs(uv[1]-uv[0]);walls.append(i)
            elif s.GetType()==GeomAbs_Plane:
                plane=s.Plane()
                if abs(abs(np.dot(axis,xyz(plane.Axis().Direction())))-1)>1e-8:raise ValueError('channel reaches nonperpendicular plane')
                ww=shape_map(face,TopAbs_WIRE);outer_wire=BRepTools.OuterWire_s(face)
                try:
                    if ww.Extent()!=2:raise ValueError('not an annular shoulder')
                    for k in range(1,ww.Extent()+1):ring(TopoDS.Wire(ww.FindKey(k)),enforce_limit=False)
                    annulus=True
                except ValueError:annulus=False
                if not annulus:
                    matches=[]
                    for k in range(1,ww.Extent()+1):
                        w=TopoDS.Wire(ww.FindKey(k))
                        if w.IsSame(outer_wire):continue
                        we=shape_map(w,TopAbs_EDGE)
                        if any(owners[edges.FindIndex(we.FindKey(j))]&set(walls) for j in range(1,we.Extent()+1)):
                            ring(w);matches.append(k)
                    if len(matches)!=1:raise ValueError('channel must end in exactly one planar inner mouth')
                    ends.add((i,matches[0]));continue
                for k in range(1,ww.Extent()+1):ring(TopoDS.Wire(ww.FindKey(k)))
                shoulders.append(i)
            else:raise ValueError(f'unsupported channel surface {s.GetType()} at face {i}, entry wire {selected_wire}')
            local=shape_map(face,TopAbs_EDGE)
            for k in range(1,local.Extent()+1):
                edge=local.FindKey(k);curve=BRepAdaptor_Curve(TopoDS.Edge(edge));neighbors=owners[edges.FindIndex(edge)]
                if curve.GetType()==GeomAbs_Circle:
                    if not coaxial(curve.Circle().Axis()):raise ValueError('channel contains noncoaxial edge')
                elif curve.GetType()!=GeomAbs_Line or s.GetType() not in (GeomAbs_Cylinder,GeomAbs_Cone) or (s.GetType()==GeomAbs_Cylinder and abs(abs(np.dot(axis,xyz(curve.Line().Direction())))-1)>1e-8):raise ValueError('unsupported channel edge')
                if len(neighbors)>2:raise ValueError('nonmanifold channel edge')
                queue.extend(neighbors-{i,entry_face_index})
        if len(ends)!=2 or any(abs(turn-2*math.pi)>1e-5 for turn in turns.values()):raise ValueError('channel is not a complete two-mouth bore')
        patches=set(walls+shoulders)
        if patches&removed:raise ValueError('overlapping bore selections')
        end_positions=[float(np.dot(axis,xyz(BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(i))).Plane().Location()))) for i,_ in ends]
        if abs(end_positions[0]-end_positions[1])<1e-5:raise ValueError('coincident channel mouths')
        removed.update(patches)
        for i,j in ends:rebuild.setdefault(i,set()).add(j)
        proofs.append({'entry_wire_index':selected_wire,'wall_face_indices':sorted(walls),'shoulder_face_indices':sorted(shoulders),'end_mouths':[list(x) for x in sorted(ends)],'radii_mm':sorted({key[0] for key in turns}),'axis_direction':axis.tolist(),'axis_anchor_mm':anchor.tolist(),'end_parameters_mm':sorted(end_positions)})
    result=[];indices=[]
    for i in range(1,faces.Extent()+1):
        if i in removed:continue
        face=TopoDS.Face(faces.FindKey(i))
        if i in rebuild:
            forward=TopoDS.Face(face.Oriented(TopAbs_FORWARD));plane=BRepAdaptor_Surface(forward).Plane();ww=shape_map(forward,TopAbs_WIRE);ow=BRepTools.OuterWire_s(forward);builder=BRepBuilderAPI_MakeFace(plane,ow,True)
            for j in range(1,ww.Extent()+1):
                wire=TopoDS.Wire(ww.FindKey(j))
                if not wire.IsSame(ow) and j not in rebuild[i]:builder.Add(wire)
            rebuilt=builder.Face()
            if not BRepCheck_Analyzer(rebuilt).IsValid():raise ValueError('invalid capped end face')
            face=TopoDS.Face(rebuilt.Oriented(face.Orientation()))
        result.append(face);indices.append(i)
    return compound(result),indices,{'pass':'selected-native-axial-bore-closure-v1','strict_maximum_gap_mm':maximum_gap_mm,'entry_face_index':entry_face_index,'closed_bores':proofs,'removed_wall_and_shoulder_faces':sorted(removed),'rebuilt_end_planes':sorted(rebuild),'source_faces':faces.Extent(),'result_faces':len(result),'scope':'Explicitly selected complete cylindrical/stepped/countersunk channels. Other face identities retained. Surface compound, not solid healing or motion classification.'}


def cap_selected_recess_mesh(points_mm, triangles, triangle_srgb, features, *,
                              radial_margin_mm=1, plane_tolerance_mm=.001):
    """Close caller-identified circular recesses without re-simplifying a member.

    Each feature supplies a unit ``axis_direction``, perpendicular
    ``axis_anchor_mm``, two ``end_parameters_mm`` and native ``radii_mm``.
    Only facets entirely inside its finite radial envelope and between its end
    planes are removed; existing end-plane facets stay. The cut must expose one
    convex circular-mouth polygon with manifold incidence and one material.
    Its exact existing rim positions are retained and capped with a center fan.
    Explicit ``retain_interior=True`` features instead cap the caller-pinned
    ``mouth_parameter_mm`` without deleting any interior geometry; these visual
    covers intentionally leave nonmanifold cap/side-wall incidence.
    No untouched triangle is collapsed or moved. Native feature qualification,
    width authorization and motion ownership remain the caller's responsibility.
    """
    p=np.asarray(points_mm,float);t=np.asarray(triangles);c=np.asarray(triangle_srgb,float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or c.shape!=(len(t),3) or not np.isfinite(c).all() or np.any((c<0)|(c>1)):raise ValueError('invalid recess mesh')
    if not all(math.isfinite(v) and v>0 for v in (radial_margin_mm,plane_tolerance_mm)):raise ValueError('invalid recess envelope')
    features=list(features)
    if not features:raise ValueError('empty recess selection')
    p,inverse=np.unique(p,axis=0,return_inverse=True);t=inverse[t];corners=p[t];oriented=np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]);ee,inv,counts=np.unique(np.sort(oriented,axis=1),axis=0,return_inverse=True,return_counts=True);owners=np.tile(np.arange(len(t)),3);removed=np.zeros(len(t),bool);centers=[];caps=[];colors=[];records=[]
    for feature in features:
        axis=np.asarray(feature['axis_direction'],float);anchor=np.asarray(feature['axis_anchor_mm'],float);ends=np.asarray(feature['end_parameters_mm'],float);radii=np.asarray(feature['radii_mm'],float)
        if axis.shape!=(3,) or anchor.shape!=(3,) or ends.shape!=(2,) or radii.ndim!=1 or not len(radii) or not np.isfinite(np.r_[axis,anchor,ends,radii]).all() or abs(np.linalg.norm(axis)-1)>1e-8 or abs(anchor@axis)>1e-5 or np.any(radii<=0):raise ValueError('invalid native recess frame')
        lo,hi=sorted(ends)
        if hi-lo<=2*plane_tolerance_mm:raise ValueError('empty recess depth')
        z=corners@axis;delta=corners-anchor;radial=np.linalg.norm(delta-z[:,:,None]*axis,axis=2);on_end=(np.max(abs(z-lo),axis=1)<=plane_tolerance_mm)|(np.max(abs(z-hi),axis=1)<=plane_tolerance_mm)
        select=(radial.max(1)<=radii.max()+radial_margin_mm)&(z.min(1)>=lo-plane_tolerance_mm)&(z.max(1)<=hi+plane_tolerance_mm)&~on_end
        mouth_only=feature.get('retain_interior',False)
        if type(mouth_only) is not bool:raise ValueError('invalid mouth-only flag')
        if mouth_only:
            mouth=float(feature['mouth_parameter_mm'])
            if not math.isfinite(mouth) or min(abs(mouth-lo),abs(mouth-hi))>plane_tolerance_mm:raise ValueError('mouth outside pinned end planes')
            on_mouth=np.max(abs(z-mouth),axis=1)<=plane_tolerance_mm
            plane_incidence=np.bincount(inv,weights=on_mouth[owners],minlength=len(ee))
            edge_points=p[ee];edge_z=edge_points@axis;edge_radial=np.linalg.norm(edge_points-anchor-edge_z[:,:,None]*axis,axis=2)
            border=np.flatnonzero((counts==2)&(plane_incidence==1)&(np.max(abs(edge_z-mouth),axis=1)<=plane_tolerance_mm)&(edge_radial.max(1)<=radii.max()+radial_margin_mm))
            select=np.zeros(len(t),bool)
        elif not select.any() or np.any(select&removed):raise ValueError('empty or overlapping recess removal')
        selected_faces=np.flatnonzero(select);local_edges=inv.reshape(3,len(t))[:,selected_faces].T;edge_faces={}
        for face,ids in zip(selected_faces,local_edges):
            for edge in ids:edge_faces.setdefault(int(edge),[]).append(int(face))
        neighbors={int(face):set() for face in selected_faces}
        for fs in edge_faces.values():
            for face in fs:neighbors[face].update(set(fs)-{face})
        reached=set();pending=[int(selected_faces[0])] if len(selected_faces) else []
        while pending:
            face=pending.pop()
            if face in reached:continue
            reached.add(face);pending.extend(neighbors[face]-reached)
        if len(reached)!=len(selected_faces):raise ValueError('recess envelope includes disconnected surfaces')
        incident=np.bincount(inv,weights=select[owners],minlength=len(ee));touched=incident>0
        if np.any(counts[touched]!=2):raise ValueError('recess removal touches nonmanifold or open source edges')
        if not mouth_only:border=np.flatnonzero(incident==1)
        rim=ee[border];vertices,degree=np.unique(rim,return_counts=True)
        if len(rim)<3 or np.any(degree!=2):raise ValueError('recess does not expose a closed polygon')
        zz=p[vertices]@axis;dist=[float(np.max(abs(zz-end))) for end in (lo,hi)];mouth=(lo,hi)[int(np.argmin(dist))]
        if min(dist)>plane_tolerance_mm:raise ValueError('recess boundary is not on one native mouth plane')
        center=anchor+mouth*axis
        # A convex rim must contain the projected axis and have a consistently
        # oriented loop. Check every vertex against every directed boundary edge.
        adjacency={int(v):[] for v in vertices}
        for x,y in rim:adjacency[int(x)].append(int(y));adjacency[int(y)].append(int(x))
        loop=[int(vertices[0])];previous=None
        while True:
            choices=[v for v in adjacency[loop[-1]] if v!=previous];nxt=choices[0]
            if nxt==loop[0]:break
            if nxt in loop:raise ValueError('self-intersecting recess rim')
            previous=loop[-1];loop.append(nxt)
        if len(loop)!=len(vertices):raise ValueError('recess boundary has multiple loops')
        q=p[loop];edges_q=np.roll(q,-1,axis=0)-q;sign=np.sign(np.sum(np.cross(q-center,np.roll(q,-1,axis=0)-center)@axis))
        if sign==0:raise ValueError('degenerate recess rim')
        for point,edge in zip(q,edges_q):
            if np.min(sign*(np.cross(edge,q-point)@axis))<-1e-5 or sign*np.dot(np.cross(edge,center-point),axis)<-1e-5:raise ValueError('recess rim is not convex around native axis')
        keep_records=(on_mouth[owners] if mouth_only else ~select[owners])&np.isin(inv,border);directed=oriented[keep_records];adjacent_colors=c[owners[keep_records]]
        if len(directed)!=len(rim) or not np.all(adjacent_colors==adjacent_colors[0]) or not np.all(c[select]==adjacent_colors[0]):raise ValueError('recess crosses a material boundary')
        at=len(p)+len(centers);new=np.column_stack([directed[:,1],directed[:,0],np.full(len(directed),at)])
        capnormal=np.cross(p[new[:,1]]-p[new[:,0]],center-p[new[:,0]])@axis
        if np.any(abs(capnormal)<1e-12) or np.any(np.sign(capnormal)!=np.sign(capnormal[0])):raise ValueError('inconsistent recess winding')
        centers.append(center);caps.append(new);colors.append(np.tile(adjacent_colors[0],(len(new),1)));removed|=select;records.append({'removed_original_triangle_indices':np.flatnonzero(select).tolist(),'rim_vertices':len(vertices),'mouth_parameter_mm':mouth,'radial_envelope_mm':float(radii.max()+radial_margin_mm),'cap_triangles':len(new),'interior_retained':mouth_only})
    retained=np.flatnonzero(~removed);out_p=np.concatenate([p,np.array(centers)]);out_t=np.concatenate([t[retained],*caps]);out_c=np.concatenate([c[retained],*colors])
    return out_p,out_t,out_c,{'pass':'selected-recess-local-mesh-cap-v1','retained_original_triangle_indices':retained.tolist(),'removed_triangles':int(removed.sum()),'cap_triangles':sum(len(cap) for cap in caps),'features':records,'plane_tolerance_mm':plane_tolerance_mm,'radial_margin_mm':radial_margin_mm,'scope':'Exact retained triangle positions and colours; selected recess interiors replaced by caps on their existing convex mouth rims. Not source-solid healing or an unqualified hole detector.'}
