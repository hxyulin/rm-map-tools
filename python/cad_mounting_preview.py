# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-bound in-memory mounting previews with original native face appearance.

Only explicit circular mouths and matched hardware units are eligible. Native
ordinals remain checksum-scoped, and geometric binding never invents STEP IDs.
Original CAD, installed assets and collision are unchanged.
"""
from collections import defaultdict,Counter
import math
import numpy as np
from cad_mounting_details import AnalyticDetails
from cad_wall_fill import shape_map


def _circle_key(center,radius):return tuple(np.round(np.r_[center,radius],4))


def _hardware_key(bounds,count,radii,origin,direction):
    axis=np.asarray(direction,float);axis=axis/np.linalg.norm(axis)
    if axis[np.argmax(abs(axis))]<0:axis=-axis
    anchor=np.asarray(origin)-axis*(np.asarray(origin)@axis)
    return (count,tuple(np.round(np.asarray(bounds).ravel(),4)),tuple(sorted(set(round(r,5) for r in radii))),tuple(np.round(np.r_[anchor,axis],4)))


def bind_details(document,root,openings,fasteners):
    """Qualify source circles and whole hardware shells against original native CAD.

    Circle binding requires a complete native inner circle at the source center
    and radius. Hardware binding requires matching conservative finite edge
    bounds, face count, coaxial support/radii/axis, and equal source/native
    multiplicity. Unresolved hardware groups are withheld, never guessed.
    """
    from OCP.TopAbs import TopAbs_FACE,TopAbs_WIRE,TopAbs_EDGE,TopAbs_SHELL
    from OCP.TopoDS import TopoDS
    from OCP.BRepTools import BRepTools
    from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_Plane,GeomAbs_Circle,GeomAbs_Cylinder,GeomAbs_Line
    faces=shape_map(root,TopAbs_FACE);shells=shape_map(root,TopAbs_SHELL);circles=defaultdict(list);bindings={};matched_mouths=set()
    for row in openings:
        if row['kind']!='circular-opening':raise ValueError('preview only admits explicit circular openings')
        circles[_circle_key(row['center_mm'],row['diameter_mm']/2)].append(row)
    for i in range(1,faces.Extent()+1):
        face=TopoDS.Face(faces.FindKey(i))
        if BRepAdaptor_Surface(face).GetType()!=GeomAbs_Plane:continue
        outer=BRepTools.OuterWire_s(face);wires=shape_map(face,TopAbs_WIRE)
        for j in range(1,wires.Extent()+1):
            wire=TopoDS.Wire(wires.FindKey(j))
            if wire.IsSame(outer):continue
            edges=shape_map(wire,TopAbs_EDGE);keys=[];radius=None
            for k in range(1,edges.Extent()+1):
                curve=BRepAdaptor_Curve(TopoDS.Edge(edges.FindKey(k)))
                if curve.GetType()!=GeomAbs_Circle:break
                circle=curve.Circle();p=circle.Location();radius=circle.Radius();keys.append(_circle_key([p.X(),p.Y(),p.Z()],radius))
            else:
                if not keys or len(set(keys))!=1 or keys[0] not in circles:continue
                props=GProp_GProps();BRepGProp.LinearProperties_s(wire,props)
                if abs(props.Mass()-2*math.pi*radius)>1e-5:continue
                bindings.setdefault(i,[]).append((j,circles[keys[0]]));matched_mouths.update((r['source_face_id'],r['source_bound_id']) for r in circles[keys[0]])
    source=defaultdict(list);analytic=AnalyticDetails(document);ix=document.index
    for record in fasteners:
        bounds=[]
        for face in record['source_face_ids']:
            for bound in analytic.refs(face)[:-1]:
                loop=analytic.refs(bound)[0];bounds.append(analytic.loop(loop)[1])
        points=np.concatenate(bounds);key=_hardware_key([points.min(0),points.max(0)],len(record['source_face_ids']),record['radius_values_mm'],record['axis_origin_mm'],record['axis_direction']);source[key].append(record)
    native=defaultdict(list)
    for i in range(1,shells.Extent()+1):
        shell=shells.FindKey(i);local=shape_map(shell,TopAbs_FACE)
        if local.Extent()>256:continue
        supports=[];bounds=[];supported=True
        for j in range(1,local.Extent()+1):
            surface=BRepAdaptor_Surface(TopoDS.Face(local.FindKey(j)))
            if surface.GetType()==GeomAbs_Cylinder:supports.append(surface.Cylinder())
        if not supports:continue
        edges=shape_map(shell,TopAbs_EDGE)
        for j in range(1,edges.Extent()+1):
            curve=BRepAdaptor_Curve(TopoDS.Edge(edges.FindKey(j)))
            if curve.GetType()==GeomAbs_Line:
                for u in [curve.FirstParameter(),curve.LastParameter()]:p=curve.Value(u);bounds.append([p.X(),p.Y(),p.Z()])
            elif curve.GetType()==GeomAbs_Circle:
                circle=curve.Circle();p=circle.Location();n=circle.Axis().Direction();center=np.array([p.X(),p.Y(),p.Z()]);axis=np.array([n.X(),n.Y(),n.Z()]);extent=circle.Radius()*np.sqrt(np.maximum(0,1-axis**2));bounds.extend([center-extent,center+extent])
            else:supported=False;break
        if not supported or not bounds:continue
        points=np.array(bounds);axis=supports[0].Axis();p=axis.Location();n=axis.Direction();key=_hardware_key([points.min(0),points.max(0)],local.Extent(),[c.Radius() for c in supports],[p.X(),p.Y(),p.Z()],[n.X(),n.Y(),n.Z()]);native[key].append(i)
    dropped=set();hardware_bindings=[];withheld=[]
    for key,records in source.items():
        shells_found=native.get(key,[])
        if len(shells_found)!=len(records):withheld.extend(r['source_unit_id'] for r in records);continue
        local_faces=[]
        for shell in shells_found:
            local=shape_map(shells.FindKey(shell),TopAbs_FACE)
            for j in range(1,local.Extent()+1):dropped.add(faces.FindIndex(local.FindKey(j)));local_faces.append(faces.FindIndex(local.FindKey(j)))
        hardware_bindings.append({'source_unit_ids':[r['source_unit_id'] for r in records],'native_shell_indices':shells_found,'native_face_indices':sorted(set(local_faces)),'equal_multiplicity':True})
    proof={'source_sha256':document.source_sha256,'selected_opening_mouths':len(openings),'matched_source_opening_mouths':len(matched_mouths),'matched_native_inner_wires':sum(len(v) for v in bindings.values()),'unmatched_source_openings':[{'source_face_id':r['source_face_id'],'source_bound_id':r['source_bound_id']} for r in openings if (r['source_face_id'],r['source_bound_id']) not in matched_mouths],'hole_bindings':[{'native_face_index':i,'native_inner_wire_indices':[j for j,_ in rows],'source_openings':[{'source_face_id':r['source_face_id'],'source_bound_id':r['source_bound_id']} for _,items in rows for r in items]} for i,rows in bindings.items()],'hardware_bindings':hardware_bindings,'withheld_source_fastener_unit_ids':withheld,'scope':'Geometric native/source correspondence with explicit original STEP selectors; local native ordinals are not STEP IDs. Unmatched candidates withheld. No source CAD edits.'}
    return {'faces':faces,'holes':bindings,'dropped':dropped,'proof':proof}


def preview_mesh(points,triangles,material_ids,palette,triangle_faces,bindings,*,fill_holes=False,remove_fasteners=False):
    """Retain exact input triangles/paint and replace only selected planar faces.

    Rebuilt faces reuse their own original resolved native face colour. No edited
    STEP re-import or inherited-colour recovery is needed. Hidden bore walls stay
    intact, so this is a visual preview rather than valid-solid defeaturing.
    """
    from OCP.TopoDS import TopoDS
    from OCP.BRepTools import BRepTools
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.TopAbs import TopAbs_WIRE,TopAbs_FACE,TopAbs_FORWARD
    from OCP.BRepCheck import BRepCheck_Analyzer
    from cad_detail_passes import mesh_native_detail
    p=np.asarray(points);t=np.asarray(triangles);m=np.asarray(material_ids);owners=np.asarray(triangle_faces);drop=bindings['dropped'] if remove_fasteners else set();changed=set(bindings['holes'])-drop if fill_holes else set();prepared=[];patches=[];withheld=[]
    for index in sorted(changed):
        original=TopoDS.Face(bindings['faces'].FindKey(index));face=TopoDS.Face(original.Oriented(TopAbs_FORWARD));colour_ids=set(map(int,m[owners==index]))
        if len(colour_ids)!=1:raise ValueError('source native face paint is ambiguous')
        colour_id=next(iter(colour_ids));surface=BRepAdaptor_Surface(face);outer=BRepTools.OuterWire_s(face);maker=BRepBuilderAPI_MakeFace(surface.Plane(),outer,True);wires=shape_map(face,TopAbs_WIRE);removed={j for j,_ in bindings['holes'][index]}
        for j in range(1,wires.Extent()+1):
            wire=TopoDS.Wire(wires.FindKey(j))
            if not wire.IsSame(outer) and j not in removed:maker.Add(wire)
        cap=TopoDS.Face(maker.Face().Oriented(original.Orientation()))
        if not BRepCheck_Analyzer(cap).IsValid():withheld.append({'native_face_index':index,'reason':'Invalid reconstructed native profile; original triangles retained.'});continue
        try:cp,ct,_,_,proof=mesh_native_detail(cap,[palette[colour_id]],linear_deflection_mm=.4,angular_deflection_rad=.6)
        except ValueError as error:withheld.append({'native_face_index':index,'reason':str(error)});continue
        prepared.append((index,colour_id,cp,ct));patches.append({'source_native_face_index':index,'source_colour':palette[colour_id],'removed_inner_wires':len(removed),'before_triangles':int((owners==index).sum()),'after_triangles':len(ct),'source_paint_retained':True})
    accepted={index for index,_,_,_ in prepared};keep=~np.isin(owners,list(drop|accepted));pp=[p];tt=[t[keep]];mm=[m[keep]];ff=[owners[keep]];offset=len(p)
    for index,colour_id,cp,ct in prepared:pp.append(cp);tt.append(ct+offset);mm.append(np.full(len(ct),colour_id));ff.append(np.full(len(ct),-index));offset+=len(cp)
    return np.concatenate(pp),np.concatenate(tt),np.concatenate(mm),np.concatenate(ff),{'unchanged_input_triangle_indices':np.flatnonzero(keep).tolist(),'removed_native_faces':sorted(drop),'rebuilt_faces':patches,'withheld_hole_faces':withheld,'scope':'Exact unselected input triangle positions/material IDs retained. Selected planar loops filled in native memory with the original face colour. Invalid profiles withheld. Hidden bore-wall surfaces may remain; not a collision or valid-solid output.'}
