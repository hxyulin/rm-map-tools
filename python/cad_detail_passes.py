# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Native interior removal and bounded detail smoothing with explicit evidence.

These passes derive candidates from source B-reps. No sampled camera observation
can authorize geometry removal. Caller-owned identities and appearance remain
separate from the native shapes; source and motion policy must be pinned outside.
"""
from dataclasses import dataclass
import math
import numpy as np
from cad_wall_fill import shape_map,volume,_boolean,_propagate


def compound(shapes):
    """Build a native compound without welding or changing its source members."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    result=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(result)
    for shape in shapes:builder.Add(result,shape)
    return result


def area(shape):
    """Measure native surface area in square source millimetres."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props=GProp_GProps();BRepGProp.SurfaceProperties_s(shape,props);return abs(float(props.Mass()))


def enclosed(inner,opaque,*,clearance_mm=.001,area_tolerance_mm2=1e-6):
    """Prove a whole surface lies strictly inside valid opaque solid material.

    Uses native Boolean difference of the complete finite surfaces and minimum
    distance to the occluder's boundary. Bounding boxes and point samples cannot
    pass this test. The guarantee applies while the two shapes keep their source
    relative placement; the caller must protect independently moving members.
    """
    from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    if not all(math.isfinite(v) and v>0 for v in (clearance_mm,area_tolerance_mm2)):raise ValueError('invalid enclosure policy')
    if shape_map(opaque,TopAbs_SOLID).Extent()!=1 or not BRepCheck_Analyzer(opaque).IsValid():raise ValueError('opaque enclosure must be one valid solid')
    if area(inner)<=area_tolerance_mm2:raise ValueError('empty enclosure candidate')
    outside=_boolean(BRepAlgoAPI_Cut,inner,opaque).Shape();outside_area=area(outside)
    if outside_area>area_tolerance_mm2:return {'accepted':False,'outside_area_mm2':outside_area,'reason':'finite surface extends outside opaque material'}
    faces=shape_map(opaque,TopAbs_FACE);boundary=compound(faces.FindKey(i) for i in range(1,faces.Extent()+1))
    distance=BRepExtrema_DistShapeShape(inner,boundary);distance.Perform()
    if not distance.IsDone():raise ValueError('native boundary distance failed')
    value=float(distance.Value())
    return {'accepted':value>clearance_mm,'outside_area_mm2':outside_area,'minimum_boundary_distance_mm':value,
            'required_clearance_mm':clearance_mm,'reason':'strict native material containment' if value>clearance_mm else 'touching or too near external boundary'}


@dataclass(frozen=True)
class DetailResult:
    """Derived native shape, appearance ledger and pass-specific checks."""
    shape: object
    face_colours: tuple
    source_face_indices: tuple
    proof: dict


def fill_enclosed_voids(source,source_colours,*,clearance_mm=.001):
    """Omit only closed cavity shells strictly inside the retained outer solid.

    Exterior faces are retained by native identity, so their trims and appearance
    are unchanged. Closed cavities become opaque material; no exterior hole is
    capped. Invalid outer shells or touching/internal shells reject the pass.
    """
    from OCP.TopAbs import TopAbs_FACE,TopAbs_SHELL,TopAbs_SOLID
    from OCP.TopoDS import TopoDS
    from OCP.BRepClass3d import BRepClass3d
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
    from OCP.BRepCheck import BRepCheck_Analyzer
    if shape_map(source,TopAbs_SOLID).Extent()!=1:raise ValueError('void pass needs one source solid')
    faces=shape_map(source,TopAbs_FACE)
    if len(source_colours)!=faces.Extent():raise ValueError('incomplete source appearance')
    outer=BRepClass3d.OuterShell_s(TopoDS.Solid(shape_map(source,TopAbs_SOLID).FindKey(1)));result=BRepBuilderAPI_MakeSolid(outer).Solid()
    if not BRepCheck_Analyzer(result).IsValid() or volume(result)<=0:raise ValueError('retained outer shell is not a valid outward solid')
    shells=shape_map(source,TopAbs_SHELL);dropped=[]
    for i in range(1,shells.Extent()+1):
        shell=shells.FindKey(i)
        if shell.IsSame(outer):continue
        proof=enclosed(shell,result,clearance_mm=clearance_mm)
        if not proof['accepted']:raise ValueError('cavity shell is not strictly enclosed')
        dropped.append(proof)
    new=shape_map(result,TopAbs_FACE);ids=[faces.FindIndex(new.FindKey(i)) for i in range(1,new.Extent()+1)]
    if any(i==0 for i in ids):raise ValueError('void pass changed an exterior face identity')
    return DetailResult(result,tuple(source_colours[i-1] for i in ids),tuple((i,) for i in ids),{
        'pass':'fill-enclosed-voids-v1','source_faces':faces.Extent(),'result_faces':new.Extent(),'removed_cavity_shells':len(dropped),
        'retained_exterior_faces_unchanged':True,'cavity_checks':dropped,'source_was_valid':BRepCheck_Analyzer(source).IsValid(),
        'result_valid':True,'source_volume_mm3':volume(source),'result_volume_mm3':volume(result),
        'scope':'Closed source cavities filled; exact native outer-face identities retained. Relative motion policy remains caller-owned.'})


def small_bore_groups(source,*,maximum_radius_mm=3,maximum_depth_mm=25):
    """Discover complete adjacent cylindrical bores between planar inner wires.

    Split half/quarter-cylinder faces are grouped by native edge incidence and
    coincident analytic axis. The sum of angular spans must cover one full turn;
    conical, curved-ended, intersecting and unresolved groups are left untouched.
    Discovery is not permission to smooth arbitrary functional holes.
    """
    from OCP.TopAbs import TopAbs_FACE,TopAbs_EDGE,TopAbs_REVERSED
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools
    from OCP.GeomAbs import GeomAbs_Cylinder,GeomAbs_Plane,GeomAbs_Circle
    if not all(math.isfinite(x) and x>0 for x in (maximum_radius_mm,maximum_depth_mm)):raise ValueError('invalid bore discovery budget')
    faces=shape_map(source,TopAbs_FACE);edges=shape_map(source,TopAbs_EDGE);owners={};records={};keys={}
    for i in range(1,faces.Extent()+1):
        face=TopoDS.Face(faces.FindKey(i));local=shape_map(face,TopAbs_EDGE)
        for j in range(1,local.Extent()+1):owners.setdefault(edges.FindIndex(local.FindKey(j)),set()).add(i)
        surface=BRepAdaptor_Surface(face)
        if surface.GetType()!=GeomAbs_Cylinder or face.Orientation()!=TopAbs_REVERSED:continue
        cylinder=surface.Cylinder();radius=cylinder.Radius();uv=BRepTools.UVBounds_s(face)
        if radius>maximum_radius_mm or uv[3]-uv[2]>maximum_depth_mm:continue
        axis=cylinder.Axis();direction=np.array([axis.Direction().X(),axis.Direction().Y(),axis.Direction().Z()]);origin=np.array([axis.Location().X(),axis.Location().Y(),axis.Location().Z()])
        if direction[np.argmax(abs(direction))]<0:direction=-direction
        anchor=origin-direction*np.dot(origin,direction);key=tuple(np.round(np.r_[anchor,radius,direction],5))
        keys[i]=key;records[i]=(radius,uv,direction,origin)
    visited=set();groups=[]
    for seed in records:
        if seed in visited:continue
        group={seed};todo=[seed]
        while todo:
            i=todo.pop();local=shape_map(faces.FindKey(i),TopAbs_EDGE)
            for j in range(1,local.Extent()+1):
                for n in owners[edges.FindIndex(local.FindKey(j))]:
                    if n in records and keys[n]==keys[seed] and n not in group:group.add(n);todo.append(n)
        visited.update(group)
        if abs(sum(records[i][1][1]-records[i][1][0] for i in group)-2*np.pi)>1e-5:continue
        ends=set();supported=True
        for i in group:
            local=shape_map(faces.FindKey(i),TopAbs_EDGE)
            for j in range(1,local.Extent()+1):
                edge=local.FindKey(j);others=owners[edges.FindIndex(edge)]-group
                for n in others:
                    neighbor=TopoDS.Face(faces.FindKey(n));surf=BRepAdaptor_Surface(neighbor)
                    if surf.GetType()!=GeomAbs_Plane or BRepAdaptor_Curve(TopoDS.Edge(edge)).GetType()!=GeomAbs_Circle or shape_map(BRepTools.OuterWire_s(neighbor),TopAbs_EDGE).Contains(edge):supported=False;break
                    normal=surf.Plane().Axis().Direction();d=records[i][2]
                    if abs(abs(np.dot(d,[normal.X(),normal.Y(),normal.Z()]))-1)>1e-8:supported=False;break
                    ends.add(n)
        if supported and len(ends)==2:
            points=[]
            for i in group:
                cylinder=BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(i))).Cylinder();axis=cylinder.Axis();o=np.array([axis.Location().X(),axis.Location().Y(),axis.Location().Z()]);d=np.array([axis.Direction().X(),axis.Direction().Y(),axis.Direction().Z()])
                points.extend(o+d*v for v in records[i][1][2:])
            canonical=records[seed][2];o=records[seed][3];parameter=np.array(points)@canonical
            start=o+canonical*(parameter.min()-np.dot(o,canonical));end=o+canonical*(parameter.max()-np.dot(o,canonical))
            groups.append({'face_indices':sorted(group),'adjacent_plane_indices':sorted(ends),'radius_mm':records[seed][0],
                           'axis_origin_mm':records[seed][3].tolist(),'axis_direction':records[seed][2].tolist(),
                           'start_mm':start.tolist(),'end_mm':end.tolist(),'depth_mm':float(np.linalg.norm(end-start))})
    return groups


def smooth_bores(source,source_colours,groups,*,maximum_added_volume_mm3,volume_tolerance_mm3=.01):
    """Close selected complete bore features, rejecting changes beyond their boxes.

    Native defeaturing may fail or modify more than requested. Validity, original
    material retention, per-feature bounds and source appearance history must all
    pass before the result is accepted. The caller pins source IDs and selection.
    """
    from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing,BRepAlgoAPI_Cut
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    if not groups or not math.isfinite(maximum_added_volume_mm3) or maximum_added_volume_mm3<=0 or not math.isfinite(volume_tolerance_mm3) or volume_tolerance_mm3<=0:raise ValueError('invalid or empty bore policy')
    faces=shape_map(source,TopAbs_FACE)
    if len(source_colours)!=faces.Extent() or not BRepCheck_Analyzer(source).IsValid():raise ValueError('bore pass needs valid source and complete appearance')
    op=BRepAlgoAPI_Defeaturing();op.SetShape(source);op.SetToFillHistory(True);selected=set();regions=[]
    for group in groups:
        bounds=Bnd_Box()
        for i in group['face_indices']:
            if i in selected or i<1 or i>faces.Extent():raise ValueError('invalid/overlapping bore face selection')
            selected.add(i);op.AddFaceToRemove(faces.FindKey(i));BRepBndLib.AddOptimal_s(faces.FindKey(i),bounds,False,False)
        lo=bounds.CornerMin();hi=bounds.CornerMax();margin=1e-4
        regions.append(BRepPrimAPI_MakeBox(gp_Pnt(lo.X()-margin,lo.Y()-margin,lo.Z()-margin),hi.X()-lo.X()+2*margin,hi.Y()-lo.Y()+2*margin,hi.Z()-lo.Z()+2*margin).Shape())
    op.Build()
    if not op.IsDone():raise ValueError('native bore defeaturing failed')
    result=op.Shape();new=shape_map(result,TopAbs_FACE)
    if not BRepCheck_Analyzer(result).IsValid() or shape_map(result,TopAbs_SOLID).Extent()!=1:raise ValueError('bore smoothing produced invalid topology')
    labels=[(source_colours[i-1],(i,)) for i in range(1,faces.Extent()+1)];mapping=_propagate(faces,new,op,labels);colours=[];sources=[]
    for i in range(1,new.Extent()+1):
        items=[x for x in mapping[i] if not set(x[1])<=selected];keys={x[0] for x in items}
        if len(keys)!=1:raise ValueError('bore smoothing lost or merged source paint')
        colours.append(next(iter(keys)));sources.append(tuple(sorted({j for _,ids in items for j in ids})))
    added=_boolean(BRepAlgoAPI_Cut,result,source).Shape();removed=_boolean(BRepAlgoAPI_Cut,source,result).Shape()
    addition=volume(added);loss=volume(removed);outside=volume(_boolean(BRepAlgoAPI_Cut,added,compound(regions)).Shape())
    if addition<=volume_tolerance_mm3 or addition>maximum_added_volume_mm3+volume_tolerance_mm3 or abs(loss)>volume_tolerance_mm3 or abs(outside)>volume_tolerance_mm3:raise ValueError('bore smoothing exceeded additive feature bounds')
    return DetailResult(result,tuple(colours),tuple(sources),{'pass':'smooth-bounded-bores-v1','source_faces':faces.Extent(),'result_faces':new.Extent(),'bores':len(groups),
        'added_volume_mm3':addition,'removed_volume_mm3':loss,'added_outside_feature_boxes_mm3':outside,'volume_tolerance_mm3':volume_tolerance_mm3,'result_valid':True})


def mesh_native_detail(shape,face_colours,*,linear_deflection_mm=.1,angular_deflection_rad=.6):
    """Tessellate a complete source unit with one native shared-edge network.

    Native surfaces, topology and face appearance are unchanged. Settings are
    mesher requests, not certified continuous deviation bounds. All faces must
    produce triangles; the source-unit caller must validate quality and seams.
    """
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ColorSurf
    from OCP.Quantity import Quantity_Color,Quantity_TOC_sRGB
    from mesh_parts import tessellate
    if not math.isfinite(linear_deflection_mm) or not math.isfinite(angular_deflection_rad) or linear_deflection_mm<=0 or not 0<angular_deflection_rad<np.pi:raise ValueError('invalid detail meshing quality')
    faces=shape_map(shape,TopAbs_FACE)
    if len(face_colours)!=faces.Extent():raise ValueError('incomplete detail mesh appearance')
    doc=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'));XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).AddShape(shape,False);ct=XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    for i,key in enumerate(face_colours,1):
        if key is not None:ct.SetColor(faces.FindKey(i),Quantity_Color(*map(float,key.split(',')),Quantity_TOC_sRGB),XCAFDoc_ColorSurf)
    records=[];stats={}
    points,triangles,ci,colours=tessellate(doc,linear_deflection_mm,angular_deflection_rad,stats,lambda i,f,n:records.append((f,n)))
    if stats.get('unmeshed_faces') or len(records)!=faces.Extent() or any(n==0 for _,n in records):raise ValueError('native detail mesh omitted a finite face')
    triangle_faces=[]
    for f,n in records:
        index=faces.FindIndex(f)
        if not index:raise ValueError('detail mesh changed native face ownership')
        triangle_faces.extend([index]*n)
    if len(triangle_faces)!=len(triangles):raise ValueError('detail face accounting mismatch')
    return points,triangles,[colours[int(i)] for i in ci],np.array(triangle_faces,dtype=np.uint32),{
        'source_faces':faces.Extent(),'triangles':len(triangles),'linear_deflection_mm':linear_deflection_mm,
        'angular_deflection_rad':angular_deflection_rad,'source_topology_unchanged':True,'all_faces_meshed':True,'stats':stats}


def sampled_support_error(shape,points_mm,triangles,triangle_faces,*,limit_mm=.12):
    """Check vertices/midpoints/centroids against native analytic face supports.

    All such points are checked for analytic planes, cylinders, cones, spheres
    and tori. Other supports use at most 64 deterministic points per source face
    with native projection. This is a support check, not a trim-domain/Hausdorff
    certificate or a substitute for the mesher's shared boundary network.
    """
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.gp import gp_Pnt
    if not math.isfinite(limit_mm) or limit_mm<=0:raise ValueError('invalid support error limit')
    faces=shape_map(shape,TopAbs_FACE);maximum=0.;count=0;fallback=0
    xyz=lambda p:np.array([p.X(),p.Y(),p.Z()])
    for i in np.unique(triangle_faces):
        face=TopoDS.Face(faces.FindKey(int(i)));s=BRepAdaptor_Surface(face);kind=str(s.GetType()).rsplit('_',1)[-1]
        corners=points_mm[triangles[triangle_faces==i]];p=np.concatenate([corners.reshape(-1,3),corners.mean(1),(corners[:,0]+corners[:,1])/2,(corners[:,1]+corners[:,2])/2,(corners[:,2]+corners[:,0])/2])
        if kind=='Plane':
            plane=s.Plane();error=abs((p-xyz(plane.Location()))@xyz(plane.Axis().Direction()))
        elif kind in ('Cylinder','Cone','Torus'):
            surface=getattr(s,kind)();axis=surface.Axis();local=p-xyz(axis.Location());z=local@xyz(axis.Direction());rho=np.sqrt(np.maximum(0,np.sum(local*local,1)-z*z))
            if kind=='Cylinder':error=abs(rho-surface.Radius())
            elif kind=='Cone':error=abs(rho*np.cos(surface.SemiAngle())-z*np.sin(surface.SemiAngle())-surface.RefRadius()*np.cos(surface.SemiAngle()))
            else:error=abs(np.sqrt((rho-surface.MajorRadius())**2+z*z)-surface.MinorRadius())
        elif kind=='Sphere':error=abs(np.linalg.norm(p-xyz(s.Sphere().Location()),axis=1)-s.Sphere().Radius())
        else:
            p=p[np.linspace(0,len(p)-1,min(64,len(p)),dtype=int)];surface=BRep_Tool.Surface_s(face);uv=BRepTools.UVBounds_s(face);values=[]
            for q in p:
                projection=GeomAPI_ProjectPointOnSurf(gp_Pnt(*q),surface,*uv,1e-8)
                if projection.NbPoints()==0:raise ValueError('native support projection failed')
                values.append(projection.LowerDistance())
            error=np.array(values);fallback+=len(p)
        worst=float(error.max(initial=0));maximum=max(maximum,worst);count+=len(p)
        if worst>limit_mm:raise ValueError(f'native support deviation {worst} exceeds {limit_mm} mm on face {i}')
    return {'maximum_sampled_support_error_mm':maximum,'sampled_points':count,'nonanalytic_projected_samples':fallback,'limit_mm':limit_mm,
            'scope':'Native support samples; not continuous finite trimmed-face equivalence.'}


def plug_bores(source,source_colours,groups,*,maximum_added_volume_mm3,radial_overlap_mm=1e-5):
    """Smooth reviewed straight fastener bores by union with finite native plugs.

    The result is source ∪ plugs: change extent is bounded by construction. Each
    plug spans the two source planar ends and overlaps its bore wall radially by
    the explicit tiny allowance. Source-plane diffuse paint is carried to caps;
    coplanar unification protects differing colors. Complete native differences
    are deliberately not claimed for this constructive pass. Actual volume gain
    must be positive and no larger than total plug volume and caller budget.
    """
    from OCP.TopAbs import TopAbs_FACE,TopAbs_EDGE,TopAbs_SOLID
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.collections import List_TopoDS_Shape
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Ax2,gp_Pnt,gp_Dir
    if not groups or not math.isfinite(maximum_added_volume_mm3) or maximum_added_volume_mm3<=0 or not 0<radial_overlap_mm<=1e-4:raise ValueError('invalid plug policy')
    faces=shape_map(source,TopAbs_FACE)
    if len(source_colours)!=faces.Extent() or not BRepCheck_Analyzer(source).IsValid():raise ValueError('plug source must be valid with complete appearance')
    available={tuple(g['face_indices']):g for g in small_bore_groups(source)}
    tools=[];tool_labels=[];tool_faces=[];seen=set();total_volume=0.
    for group in groups:
        key=tuple(group['face_indices'])
        if key not in available or key in seen or group!=available[key]:raise ValueError('plug selection is not a complete native bore')
        seen.add(key);start=np.array(group['start_mm']);end=np.array(group['end_mm']);direction=(end-start)/np.linalg.norm(end-start)
        shape=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*start),gp_Dir(*direction)),group['radius_mm']+radial_overlap_mm,group['depth_mm']).Shape();tools.append(shape);total_volume+=volume(shape);local=shape_map(shape,TopAbs_FACE)
        for i in range(1,local.Extent()+1):
            f=TopoDS.Face(local.FindKey(i));surface=BRepAdaptor_Surface(f);colour=source_colours[group['face_indices'][0]-1]
            if surface.GetType()==GeomAbs_Plane:
                origin=surface.Plane().Location();choices=[]
                for j in group['adjacent_plane_indices']:
                    plane=BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(j))).Plane();choices.append((abs(plane.Distance(origin)),source_colours[j-1]))
                colour=min(choices,key=lambda x:x[0])[1]
            tool_faces.append(f);tool_labels.append((colour,()))
    args=List_TopoDS_Shape();args.Append(source);tools_list=List_TopoDS_Shape()
    for shape in tools:tools_list.Append(shape)
    fuse=BRepAlgoAPI_Fuse();fuse.SetArguments(args);fuse.SetTools(tools_list);fuse.SetNonDestructive(True);fuse.Build()
    if not fuse.IsDone():raise ValueError('native plug union failed')
    raw=fuse.Shape();raw_faces=shape_map(raw,TopAbs_FACE);mapping=_propagate(faces,raw_faces,fuse,[(c,(i,)) for i,c in enumerate(source_colours,1)])
    tool_map=_propagate(shape_map(compound(tools),TopAbs_FACE),raw_faces,fuse,tool_labels);labels=[]
    for i in range(1,raw_faces.Extent()+1):
        items=mapping[i] or tool_map[i];colours={c for c,_ in items}
        if len(colours)!=1:raise ValueError('plug union lost/mixed face appearance')
        labels.append((next(iter(colours)),tuple(sorted({j for _,ids in items for j in ids}))))
    unify=ShapeUpgrade_UnifySameDomain(raw,True,True,False);unify.SetSafeInputMode(True);edges=shape_map(raw,TopAbs_EDGE);owners={}
    for i in range(1,raw_faces.Extent()+1):
        local=shape_map(raw_faces.FindKey(i),TopAbs_EDGE)
        for j in range(1,local.Extent()+1):owners.setdefault(edges.FindIndex(local.FindKey(j)),set()).add(i)
    for i,uses in owners.items():
        if len({labels[j-1][0] for j in uses})>1:unify.KeepShape(edges.FindKey(i))
    unify.Build();result=unify.Shape();new=shape_map(result,TopAbs_FACE);history=_propagate(raw_faces,new,unify.History(),labels);colours=[];sources=[]
    for i in range(1,new.Extent()+1):
        items=history[i];keys={c for c,_ in items}
        if len(keys)!=1:raise ValueError('plug unification lost source appearance')
        colours.append(next(iter(keys)));sources.append(tuple(sorted({j for _,ids in items for j in ids})))
    gain=volume(result)-volume(source)
    if not BRepCheck_Analyzer(result).IsValid() or shape_map(result,TopAbs_SOLID).Extent()!=1 or gain<=.01 or gain>min(total_volume,maximum_added_volume_mm3)+.01:raise ValueError('plug result failed validity or volume budget')
    return DetailResult(result,tuple(colours),tuple(sources),{'pass':'native-bore-plugs-v1','source_faces':faces.Extent(),'result_faces':new.Extent(),'bores':len(groups),'added_volume_mm3':gain,'plug_volume_bound_mm3':total_volume,'radial_overlap_mm':radial_overlap_mm,'result_valid':True,'change_scope':'Constructive source union finite native plugs. Full complex-source difference not measured; no numeric outside-change claim.'})
