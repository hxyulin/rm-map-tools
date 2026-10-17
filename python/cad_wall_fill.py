# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explicit bounded additive wall replacement on derived native CAD solids.

This is an approximate pass: it intentionally closes reviewed apertures. It
never guesses removability from color, thinness, topology or a bounding box.
The caller owns source/component pinning, material choice and placement reuse.
"""
from collections import defaultdict
from dataclasses import dataclass
import math

import numpy as np


def shape_map(shape,kind):
    """Return a native identity map, whose indices are local to this shape."""
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    result=IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher();TopExp.MapShapes_s(shape,kind,result)
    return result


def volume(shape):
    """Measure native signed solid volume in cubic source millimetres."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    p=GProp_GProps();BRepGProp.VolumeProperties_s(shape,p);return float(p.Mass())


@dataclass(frozen=True)
class WallPanel:
    """A reviewed rectangular fill volume: origin, orthonormal axes and lengths.

    Axes are three row vectors in source millimetre coordinates; the frame must
    be right handed. The panel is solid, including front, back and end caps.
    """
    origin_mm: tuple
    axes: tuple
    lengths_mm: tuple
    colour: str | None

    def shape(self):
        """Construct a six-face native box without inferring its source scope."""
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.gp import gp_Ax2,gp_Pnt,gp_Dir
        o=np.asarray(self.origin_mm,dtype=float);a=np.asarray(self.axes,dtype=float);s=np.asarray(self.lengths_mm,dtype=float)
        if o.shape!=(3,) or a.shape!=(3,3) or s.shape!=(3,) or not all(np.isfinite(x).all() for x in (o,a,s)):
            raise ValueError('invalid wall panel parameters')
        if np.any(s<=1e-6) or not np.allclose(a@a.T,np.eye(3),rtol=0,atol=1e-12) or abs(np.linalg.det(a)-1)>1e-12:
            raise ValueError('wall panel needs a positive, right-handed orthonormal frame')
        if self.colour is not None and (not isinstance(self.colour,str) or len(self.colour.split(','))!=3 or not all(math.isfinite(float(v)) and 0<=float(v)<=1 for v in self.colour.split(','))):
            raise ValueError('explicit wall diffuse color required')
        return BRepPrimAPI_MakeBox(gp_Ax2(gp_Pnt(*o),gp_Dir(*a[2]),gp_Dir(*a[0])),*map(float,s)).Shape()


@dataclass(frozen=True)
class WallFillResult:
    """Derived B-rep and native-face appearance/source correspondence ledger."""
    shape: object
    face_colours: tuple
    source_face_indices: tuple
    proof: dict


def _boolean(operation,a,b):
    op=operation(a,b);op.SetNonDestructive(True);op.Build()
    if not op.IsDone():raise ValueError('wall Boolean operation failed')
    return op


def _propagate(old_faces,new_faces,history,labels):
    """Carry face labels through explicit native history, refusing ambiguity."""
    result=defaultdict(list)
    for i,label in enumerate(labels,1):
        old=old_faces.FindKey(i);items=list(history.Modified(old))
        if new_faces.Contains(old):items.append(old)
        for face in items:
            index=new_faces.FindIndex(face)
            if index and label not in result[index]:result[index].append(label)
    return result


def fill_wall(source,panel,source_colours,*,max_added_volume_mm3,volume_tolerance_mm3=.01):
    """Fill only an explicit panel volume, preserving original solid material.

    Native difference checks reject material removal and additions outside the
    panel. They are OCCT Boolean/volume checks at kernel tolerance, not a claim
    of bit-exact geometry or sampled Hausdorff equivalence. Paint boundaries
    between different diffuse colors are protected during coplanar unification.
    Source face indices in the ledger require a caller-pinned component checksum.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse,BRepAlgoAPI_Cut,BRepAlgoAPI_Common
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopAbs import TopAbs_FACE,TopAbs_EDGE,TopAbs_SOLID
    if not math.isfinite(max_added_volume_mm3) or max_added_volume_mm3<=0 or not math.isfinite(volume_tolerance_mm3) or volume_tolerance_mm3<=0:
        raise ValueError('invalid wall volume budget')
    if not BRepCheck_Analyzer(source).IsValid():raise ValueError('invalid source B-rep')
    original_faces=shape_map(source,TopAbs_FACE);original_solids=shape_map(source,TopAbs_SOLID)
    if original_solids.Extent()!=1 or len(source_colours)!=original_faces.Extent():raise ValueError('wall requires one source solid and complete appearance accounting')
    tool=panel.shape()
    overlap=volume(_boolean(BRepAlgoAPI_Common,source,tool).Shape())
    if overlap<=volume_tolerance_mm3:raise ValueError('panel does not overlap the source solid')
    before=volume(source);fuse=_boolean(BRepAlgoAPI_Fuse,source,tool);raw=fuse.Shape();raw_faces=shape_map(raw,TopAbs_FACE)
    labels=[(source_colours[i-1],(i,)) for i in range(1,original_faces.Extent()+1)]
    mapped=_propagate(original_faces,raw_faces,fuse,labels)
    tool_faces=shape_map(tool,TopAbs_FACE)
    tool_mapped=_propagate(tool_faces,raw_faces,fuse,[(panel.colour,())]*tool_faces.Extent())
    raw_labels=[]
    for i in range(1,raw_faces.Extent()+1):
        candidates=mapped[i]
        if not candidates and not tool_mapped[i]:raise ValueError('Boolean result face has no source or panel history')
        colours={c for c,_ in candidates}
        if len(colours)>1:raise ValueError('Boolean merged conflicting source appearances')
        raw_labels.append((next(iter(colours)) if colours else panel.colour,
                           tuple(sorted({f for _,ids in candidates for f in ids}))))
    unify=ShapeUpgrade_UnifySameDomain(raw,True,True,False);unify.SetSafeInputMode(True)
    # Never erase a color boundary merely because two supports are coplanar.
    edge_faces=defaultdict(set);edges=shape_map(raw,TopAbs_EDGE)
    for i in range(1,raw_faces.Extent()+1):
        local=shape_map(raw_faces.FindKey(i),TopAbs_EDGE)
        for j in range(1,local.Extent()+1):edge_faces[edges.FindIndex(local.FindKey(j))].add(i)
    for edge,owners in edge_faces.items():
        if len({raw_labels[i-1][0] for i in owners})>1:unify.KeepShape(edges.FindKey(edge))
    unify.Build();result=unify.Shape();faces=shape_map(result,TopAbs_FACE)
    mapping=_propagate(raw_faces,faces,unify.History(),raw_labels);colours=[];sources=[]
    for i in range(1,faces.Extent()+1):
        items=mapping[i];keys={c for c,_ in items}
        if len(keys)!=1:raise ValueError('unified face lost or mixed appearance correspondence')
        colours.append(next(iter(keys)));sources.append(tuple(sorted({f for _,ids in items for f in ids})))
    if not BRepCheck_Analyzer(result).IsValid() or shape_map(result,TopAbs_SOLID).Extent()!=1:raise ValueError('wall fill changed solid count or produced invalid topology')
    added=_boolean(BRepAlgoAPI_Cut,result,source).Shape()
    added_volume=volume(added);removed_volume=volume(_boolean(BRepAlgoAPI_Cut,source,result).Shape())
    outside=volume(_boolean(BRepAlgoAPI_Cut,added,tool).Shape())
    if added_volume<=volume_tolerance_mm3 or added_volume>max_added_volume_mm3+volume_tolerance_mm3:
        raise ValueError('wall fill added volume is empty or exceeds reviewed budget')
    if abs(removed_volume)>volume_tolerance_mm3 or abs(outside)>volume_tolerance_mm3:
        raise ValueError('wall fill changed material outside its additive panel contract')
    after=volume(result)
    if abs(after-before-added_volume)>max(volume_tolerance_mm3,abs(after)*1e-10):raise ValueError('wall volume accounting failed')
    return WallFillResult(result,tuple(colours),tuple(sources),{
        'operation':'bounded-additive-wall-fill-v1','source_faces':original_faces.Extent(),'result_faces':faces.Extent(),
        'source_volume_mm3':before,'result_volume_mm3':after,'added_volume_mm3':added_volume,
        'removed_volume_mm3':removed_volume,'added_outside_panel_volume_mm3':outside,
        'volume_tolerance_mm3':volume_tolerance_mm3,'overlap_volume_mm3':overlap,
        'valid_single_solid':True,'appearance_boundaries_preserved':True,
        'scope':'Approximate closure of explicitly reviewed apertures; native Boolean/volume checks at kernel tolerance. No original CAD mutation or runtime promotion.'})


@dataclass(frozen=True)
class FaceProfilePanel:
    """Fill apertures, or bridge notches in an explicitly selected planar profile.

    Signed depth follows the native plane axis, not the face orientation. Inner
    wires are intentionally omitted. Outer-wire mode retains the exact outline;
    convex-hull mode bridges outer concavities. An optional (u0,v0,u1,v1) window
    clips that profile in the source plane frame before extrusion. The caller
    reviews the scope, thickness and volume budget. None retains unresolved paint.
    """
    face: object
    depth_mm: float
    colour: str | None
    profile_mode: str = 'outer-wire'
    window_uv_mm: tuple | None = None

    def shape(self):
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.BRepTools import BRepTools
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
        from OCP.TopAbs import TopAbs_WIRE
        from OCP.gp import gp_Vec
        surface=BRepAdaptor_Surface(self.face)
        if surface.GetType()!=GeomAbs_Plane or self.profile_mode not in ('outer-wire','convex-hull'):
            raise ValueError('fill requires a planar face and explicit profile mode')
        if self.profile_mode=='outer-wire' and shape_map(self.face,TopAbs_WIRE).Extent()<2:
            raise ValueError('aperture fill requires interior wires')
        if not math.isfinite(self.depth_mm) or abs(self.depth_mm)<=1e-6:raise ValueError('invalid aperture fill depth')
        # Reuse explicit wall-color validation, without changing the source wire.
        WallPanel((0,0,0),((1,0,0),(0,1,0),(0,0,1)),(1,1,1),self.colour).shape()
        plane=surface.Plane();outer=BRepTools.OuterWire_s(self.face)
        if self.profile_mode=='convex-hull':outer=_convex_profile(outer,plane)
        cap=BRepBuilderAPI_MakeFace(plane,outer,True).Face()
        if self.window_uv_mm is not None:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
            from OCP.gp import gp_Pnt
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopoDS import TopoDS
            window=np.asarray(self.window_uv_mm,dtype=float)
            if window.shape!=(4,) or not np.isfinite(window).all() or window[2]<=window[0] or window[3]<=window[1]:raise ValueError('invalid profile window')
            u0,v0,u1,v1=window;frame=plane.Position();origin=frame.Location();u=frame.XDirection();v=frame.YDirection()
            polygon=BRepBuilderAPI_MakePolygon()
            for x,y in ((u0,v0),(u1,v0),(u1,v1),(u0,v1)):
                polygon.Add(gp_Pnt(origin.X()+u.X()*x+v.X()*y,origin.Y()+u.Y()*x+v.Y()*y,origin.Z()+u.Z()*x+v.Z()*y))
            polygon.Close();clip=BRepBuilderAPI_MakeFace(plane,polygon.Wire(),True).Face()
            clipped=_boolean(BRepAlgoAPI_Common,cap,clip).Shape();faces=shape_map(clipped,TopAbs_FACE)
            if faces.Extent()!=1:raise ValueError('profile window must leave one finite face')
            cap=TopoDS.Face(faces.FindKey(1))
        direction=plane.Axis().Direction()
        return BRepPrimAPI_MakePrism(cap,gp_Vec(direction)*self.depth_mm).Shape()


def _convex_profile(wire,plane):
    """Bridge only a reviewed finite straight polygon, with source hull corners."""
    from OCP.TopAbs import TopAbs_EDGE,TopAbs_VERTEX
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    edges=shape_map(wire,TopAbs_EDGE)
    if any(BRepAdaptor_Curve(TopoDS.Edge(edges.FindKey(i))).GetType()!=GeomAbs_Line for i in range(1,edges.Extent()+1)):
        raise ValueError('notch bridging requires straight polygon boundaries')
    vertices=shape_map(wire,TopAbs_VERTEX);frame=plane.Position()
    origin=np.array([frame.Location().X(),frame.Location().Y(),frame.Location().Z()])
    axes=np.array([[a.X(),a.Y(),a.Z()] for a in (frame.XDirection(),frame.YDirection(),frame.Direction())])
    points=[]
    for i in range(1,vertices.Extent()+1):
        p=BRep_Tool.Pnt_s(TopoDS.Vertex(vertices.FindKey(i)));local=(np.array([p.X(),p.Y(),p.Z()])-origin)@axes.T
        if abs(local[2])>1e-6:raise ValueError('source corner is outside selected plane')
        points.append((float(local[0]),float(local[1]),i))
    points=sorted(points)
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    def chain(items):
        result=[]
        for item in items:
            while len(result)>1 and cross(result[-2],result[-1],item)<=0:result.pop()
            result.append(item)
        return result
    hull=chain(points)[:-1]+chain(points[::-1])[:-1]
    if len(hull)<3:raise ValueError('degenerate source wall profile')
    polygon=BRepBuilderAPI_MakePolygon()
    for _,_,i in hull:polygon.Add(BRep_Tool.Pnt_s(TopoDS.Vertex(vertices.FindKey(i))))
    polygon.Close();return polygon.Wire()
