#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Coarse source-derived referee hardware, without inventing sensors or robot rigs.

Uses the existing XCAF import/color inheritance, tessellator and meshoptimizer.
Large planar panels stay planar; small mounting openings are capped on planes.
No original STEP, arena package or simulator asset is modified.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from export_field_package import GlbWriter
from mesh_parts import tessellate, face_meshes
from simplify_package import simplify_mesh
from validate_parts import read_part


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close_small_planar_holes(face, maximum_span_mm):
    """Rebuild only planar faces, retaining their outer wire and large openings.

    The threshold uses the hole's world-axis bounding span. This is an explicit
    visual approximation; new caps do not describe functional collision geometry.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_WIRE
    from OCP.TopoDS import TopoDS
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    if BRepAdaptor_Surface(face).GetType() != GeomAbs_Plane:
        return face, 0
    outer = BRepTools.OuterWire_s(face)
    keep, removed = [], 0
    wires = TopExp_Explorer(face, TopAbs_WIRE)
    while wires.More():
        wire = TopoDS.Wire(wires.Current())
        if not wire.IsSame(outer):
            bounds = Bnd_Box()
            BRepBndLib.AddOptimal_s(wire, bounds, False, False)
            lower, upper = bounds.CornerMin(), bounds.CornerMax()
            span = max(getattr(upper,axis)()-getattr(lower,axis)() for axis in ('X','Y','Z'))
            if span <= maximum_span_mm:
                removed += 1
            else:
                keep.append(wire)
        wires.Next()
    if not removed:
        return face, 0
    builder = BRepBuilderAPI_MakeFace(BRep_Tool.Surface_s(face), outer, True)
    for wire in keep:
        builder.Add(wire)
    if not builder.IsDone():
        raise ValueError('small-opening cap construction failed')
    replacement = builder.Face()
    replacement.Orientation(face.Orientation())
    return replacement, removed


def face_arrays(face, linear_mm, angular_rad):
    """Tessellate one rebuilt face in its unchanged source placement."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_REVERSED
    BRepMesh_IncrementalMesh(face, linear_mm, False, angular_rad, False)
    points, triangles, offset = [], [], 0
    for part, mesh, location in face_meshes(face, linear_mm, angular_rad, {}):
        transform = location.Transformation()
        p = []
        for i in range(1, mesh.NbNodes()+1):
            value = mesh.Node(i).Transformed(transform)
            p.append([value.X(), value.Y(), value.Z()])
        t = np.array([mesh.Triangle(i).Get() for i in range(1, mesh.NbTriangles()+1)], dtype=np.int64)-1
        if part.Orientation() == TopAbs_REVERSED:
            t = t[:, [0,2,1]]
        points.append(np.array(p)); triangles.append(t+offset); offset += len(p)
    if not triangles:
        raise ValueError('rebuilt source face did not tessellate')
    return np.concatenate(points), np.concatenate(triangles)


def assemble(parts):
    """Concatenate indexed meshes without welding distinct material regions."""
    points, triangles, colors, offset = [], [], [], 0
    for p, t, c in parts:
        points.append(p); triangles.append(t+offset); colors.extend(c); offset += len(p)
    if not triangles:
        raise ValueError('empty hardware mesh')
    return np.concatenate(points), np.concatenate(triangles), np.array(colors, dtype=np.int32)


def coarse_mesh(doc, policy, spec=None):
    """Rebuild small openings and protect large planar source faces from collapse."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    observed = []
    membership = solid_membership(doc)
    omitted = set((spec or {}).get("omit_cable_solids", []))
    p,t,c,palette = tessellate(doc, policy['tessellation_linear_mm'], policy['tessellation_angular_rad'],
        face_observer=lambda i,face,count: observed.append((i,face,count)))
    baseline = (p,t,c)
    protected, detail, cursor, capped, planar = [], [], 0, 0, 0
    for face_id, face, count in observed:
        selected = t[cursor:cursor+count]
        color = int(c[cursor]) if count else 0
        cursor += count
        if not count or membership.get(face_id, 0) in omitted:
            continue
        replacement, holes = close_small_planar_holes(face, policy['fill_hole_span_mm'])
        capped += holes
        if holes:
            q, faces = face_arrays(replacement,policy['tessellation_linear_mm'],policy['tessellation_angular_rad'])
        else:
            used, inverse = np.unique(selected,return_inverse=True)
            q, faces = p[used], inverse.reshape(-1,3)
        props = GProp_GProps(); BRepGProp.SurfaceProperties_s(face,props)
        keep = BRepAdaptor_Surface(face).GetType() == GeomAbs_Plane and props.Mass() >= policy['protected_plane_area_mm2']
        if keep:
            q, faces, _ = simplify_mesh(q,faces,policy['planar_edge_error_mm'],lock_borders=False)
        row = (q,faces,[color]*len(faces))
        (protected if keep else detail).append(row)
        planar += int(keep)
    if cursor != len(t):
        raise ValueError('source face/triangle membership is incomplete')
    outputs = list(protected)
    errors = []
    if detail:
        q, faces, materials = assemble(detail)
        for color in np.unique(materials):
            points, reduced, error = simplify_mesh(q,faces[materials==color],policy['detail_error_mm'],lock_borders=False)
            outputs.append((points,reduced,[int(color)]*len(reduced)));errors.append(error)
    return baseline, assemble(outputs), palette, {'capped_planar_openings':capped,
        'protected_planar_faces':planar,'detail_meshoptimizer_error_mm':errors,
        'error_scope':'Meshoptimizer metric for unprotected detail only; caps are intentional visual changes, not a global geometric error guarantee.'}


def solid_membership(doc):
    """Return source-scoped solid memberships matching tessellate's face ordering."""
    from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
    from OCP.TopAbs import TopAbs_SOLID,TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.collections import Sequence_TDF_Label,IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    from OCP.TopoDS import TopoDS_Compound
    from OCP.BRep import BRep_Builder
    labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels)
    root=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(root)
    for i in range(1,labels.Length()+1):builder.Add(root,XCAFDoc_ShapeTool.GetShape_s(labels.Value(i)))
    solids=IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher();faces=IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(root,TopAbs_SOLID,solids);TopExp.MapShapes_s(root,TopAbs_FACE,faces)
    membership={}
    for i in range(1,solids.Extent()+1):
        local=IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher();TopExp.MapShapes_s(solids.FindKey(i),TopAbs_FACE,local)
        for j in range(1,local.Extent()+1):membership[faces.FindIndex(local.FindKey(j))]=i
    return membership


def rough_mesh(doc,baseline,policy,spec):
    """Approximate native solid envelopes; retain explicitly protected open housings.

    Convex envelopes intentionally fill recesses and mounting holes. Small source
    details may be omitted and internal fitted hulls are discarded by containment.
    Large SM01 open-housing solids are retained to preserve the projectile passage.
    """
    from scipy.spatial import ConvexHull,QhullError,cKDTree
    membership=solid_membership(doc);owner=[]
    p,t,c,palette=tessellate(doc,policy['tessellation_linear_mm'],policy['tessellation_angular_rad'],
        face_observer=lambda i,face,count: owner.extend([membership.get(i,0)]*count))
    owner=np.array(owner);parts=[];removed=[];source_centers=p[t].mean(1)
    protected=set(spec.get('preserve_shape_solids',[]))
    omitted=set(spec.get('omit_cable_solids',[]))
    unknown=(omitted|protected)-set(owner.tolist())
    if unknown:
        raise ValueError('configured native solids missing: '+str(sorted(unknown)))
    if omitted & protected:
        raise ValueError('native solids cannot be both omitted and protected')
    for sid in np.unique(owner):
        if sid in omitted:
            removed.append({'solid':int(sid),'reason':'user-approved cable omission'});continue
        mask=owner==sid;faces=t[mask];used,inv=np.unique(faces,return_inverse=True);q=p[used];local=inv.reshape(-1,3)
        if sid not in protected and max(np.ptp(q,axis=0))<policy['omit_detail_span_mm']:
            removed.append({'solid':int(sid),'reason':'small visual detail'});continue
        if sid in protected or sid == 0:
            entries=[]
            for color in np.unique(c[mask]):
                points,reduced,error=simplify_mesh(p,faces[c[mask]==color],policy['detail_error_mm'],lock_borders=False)
                entries.append((points,reduced,[int(color)]*len(reduced)))
            q,local,colors=assemble(entries);parts.append({'id':int(sid),'mesh':(q,local,colors),'hull':None});continue
        try:
            hull=ConvexHull(q)
        except QhullError:
            # Degenerate source sheets keep their existing coarse triangles.
            q,local,_=simplify_mesh(q,local,policy['detail_error_mm'],lock_borders=False)
            colors=c[mask][cKDTree(source_centers[mask]).query(q[local].mean(1))[1]]
            parts.append({'id':int(sid),'mesh':(q,local,colors),'hull':None});continue
        triangles=hull.simplices.copy();v=q[triangles]
        normals=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]);reverse=np.sum(normals*hull.equations[:,:3],axis=1)<0
        triangles[reverse]=triangles[reverse][:,[0,2,1]]
        q,triangles,_=simplify_mesh(q,triangles,policy['detail_error_mm'],lock_borders=False)
        colors=c[mask][cKDTree(source_centers[mask]).query(q[triangles].mean(1))[1]]
        try:
            envelope=ConvexHull(q)
        except QhullError:
            envelope=None
        parts.append({'id':int(sid),'mesh':(q,triangles,colors),'hull':envelope})
    keep=[]
    for part in parts:
        q=part['mesh'][0];enclosed=False
        if part['id'] in protected or part['id'] == 0:
            keep.append(part);continue
        for other in parts:
            hull=other['hull']
            if other is part or hull is None:continue
            if np.all(q@hull.equations[:,:3].T+hull.equations[:,3]<=1e-5):
                # Prefer the earlier source solid for coincident envelopes.
                oq=other['mesh'][0]
                same=part['hull'] is not None and np.all(oq@part['hull'].equations[:,:3].T+part['hull'].equations[:,3]<=1e-5)
                if not same or other['id']<part['id']:
                    enclosed=True;removed.append({'solid':part['id'],'reason':'inside fitted solid '+str(other['id'])});break
        if not enclosed:keep.append(part)
    ranges=[];start=0
    for part in keep:
        count=len(part['mesh'][1]);ranges.append({'solid':part['id'],'triangle_start':start,'triangle_count':count});start+=count
    return assemble([part['mesh'] for part in keep]),{'triangle_ranges':ranges,'method':'per-source-solid convex envelopes, detail decimation, fitted-hull containment pruning; explicitly preserved open housing solids',
        'retained_solids':[p['id'] for p in keep],'removed_solids':removed,'preserved_shape_solids':sorted(protected),
        'material_transfer':'nearest source triangle centroid within the same solid; no invented palette'}


def export_model(source, spec, policy, out):
    if digest(source) != spec['sha256']:
        raise ValueError('source STEP checksum mismatch: '+spec['id'])
    doc,reader,error = read_part(str(source))
    if error:
        raise ValueError(error)
    baseline,coarse,palette,report = coarse_mesh(doc,policy,spec)
    rough,rough_report=rough_mesh(doc,baseline,policy,spec)
    report['rough']=rough_report
    center = (baseline[0].min(0)+baseline[0].max(0))/2
    source_to_model = np.eye(4);source_to_model[:3,3]=-center/1000
    outputs = {}
    for name,(p,t,c) in [('source',baseline),('coarse',coarse),('rough',rough)]:
        q = (p-center)/1000
        if not np.isfinite(q).all() or t.min()<0 or t.max()>=len(q):
            raise ValueError('invalid output geometry')
        path=out/(spec['id']+'-'+name+'.glb')
        writer=GlbWriter(spec['id'],{'version':'2.0','copyright':'DJI / RoboMaster source geometry; approximate hardware preview. Not licensed under the exporter software license.'})
        groups=rough_report['triangle_ranges'] if name=='rough' else [{'solid':None,'triangle_start':0,'triangle_count':len(t)}]
        for group in groups:
            start=group['triangle_start'];end=start+group['triangle_count'];selected=t[start:end]
            used,inverse=np.unique(selected,return_inverse=True)
            label='geometry' if group['solid'] is None else 'solid-'+str(group['solid'])
            writer.add_node(spec['id']+'/'+label,q[used],inverse.reshape(-1,3),[palette[k] for k in c[start:end]],extras={
                'hardware_id':spec['id'],'variant':name,'source_sha256':spec['sha256'],
                'native_solid_index':group['solid'],'semantic_role':'unclassified',
                'material_transfer':'nearest source triangle within same solid' if name=='rough' else 'source material regions',
                'collision_eligible':False,'sensor_geometry':False,'source_axes_preserved':True})
        writer.write(path)
        np.savez(out/(spec['id']+'-'+name+'.npz'),positions_mm=p-center,triangles=t,material_ids=c,palette=np.array([v or '' for v in palette]))
        outputs[name]={'file':path.name,'sha256':digest(path),'triangles':len(t),'bytes':path.stat().st_size,
            'bounds_m':[q.min(0).tolist(),q.max(0).tolist()]}
    return dict(spec,outputs=outputs,source_to_model_matrix=source_to_model.tolist(),source_colors=palette,
        appearance='source face/body colors' if all(k is not None for k in palette) else 'unstyled source: neutral gray fallback, not inferred real-world paint',
        source_dimensions_mm=np.ptp(baseline[0],axis=0).tolist(),approximation=report)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[1]/'rules/referee-hardware.json')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();config=json.loads(args.config.read_text())
    if args.out.exists():
        raise ValueError('output directory must be new')
    if any(not math.isfinite(v) or v<=0 for v in config['coarse'].values()):
        raise ValueError('coarse policy must be finite and positive')
    args.out.mkdir(parents=True)
    rows=[]
    for spec in config['models']:
        if Path(spec['source']).name != spec['source']:
            raise ValueError('source filename must not contain a path')
        row=export_model(args.sources/spec['source'],spec,config['coarse'],args.out);rows.append(row)
        print(spec['id'],row['outputs']['source']['triangles'],'->',row['outputs']['coarse']['triangles'],'rough',row['outputs']['rough']['triangles'],flush=True)
    manifest={'schema':1,'producer_sha256':digest(__file__),'policy_sha256':digest(args.config),
        'provenance':config['provenance'],'units':'metres','frame':'Original STEP axes, rebased to source bounding-box center. No mounting or sensor frame has been inferred.',
        'scope':'Visual review candidates only. No collision, scoring mask, emission, mass or physics is inferred. Raw NPZ and source GLBs are regenerable review outputs.',
        'policy':config['coarse'],'models':rows}
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (args.out/'CAD-NOTICE.md').write_text('# Referee hardware CAD\n\nSource STEP and derived geometry belong to DJI / RoboMaster and retain their original terms.\nSupplied by the user; no redistribution license is asserted. Exporter source is separately MIT OR Apache-2.0.\nThese are approximate visual prototypes, not official drawings or 2027 detector definitions.\n')

if __name__=='__main__':
    main()
