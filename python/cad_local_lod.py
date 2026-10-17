# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Spatially adaptive material LOD with shared frames and locked patch borders.

Callers own CAD provenance and selection. This reduces a tessellation of a native
source member, never inventing source-face ownership for newly joined triangles.
"""
import math
import numpy as np


def _border_positions(points, triangles):
    edges=np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1)
    edges,counts=np.unique(edges,axis=0,return_counts=True)
    return points[np.unique(edges[counts==1])]


def _contains_positions(points, expected):
    have={tuple(p) for p in points}
    return all(tuple(p) in have for p in expected)


def adaptive_material_lod(points_mm, triangles, material_ids, *, error_mm=.25,
                          sampled_limit_mm=1, sample_count=8192,
                          maximum_depth=4, minimum_patch_triangles=512):
    """Refine only spatial patches whose sampled surface check fails.

    Every trial starts from the same input tessellation, rather than repeatedly
    simplifying an earlier candidate. Material regions are independent. A failed
    region splits at its triangle-centroid median along the longest centroid
    axis. Leaf failures retry smaller error metrics, never larger guards. Border
    vertices stay locked at material and patch seams; all patches share one
    rebased float32 frame, so common seam positions remain identical. The maximum
    float32 input quantization is reported separately in millimetres.

    Returns positions, triangles, material ids and per-leaf source-triangle
    membership. Sample checks are not continuous Hausdorff/finite-CAD guarantees.
    No components or details are deliberately discarded by this policy.
    """
    from simplify_package import simplify_mesh
    from mesh_quality import deviation
    p=np.asarray(points_mm,dtype=np.float64);t=np.asarray(triangles);m=np.asarray(material_ids)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or m.shape!=(len(t),) or not np.issubdtype(m.dtype,np.integer):raise ValueError('invalid adaptive LOD mesh')
    if not all(math.isfinite(v) and v>0 for v in (error_mm,sampled_limit_mm)) or type(sample_count) is not int or not 96<=sample_count<=16384 or type(maximum_depth) is not int or not 0<=maximum_depth<=8 or type(minimum_patch_triangles) is not int or minimum_patch_triangles<16:raise ValueError('invalid adaptive LOD policy')
    origin=(p.min(0)+p.max(0))/2;quantized=np.asarray(p-origin,dtype=np.float32);q,inverse=np.unique(quantized,axis=0,return_inverse=True);qt=inverse[t];quantization=float(np.linalg.norm(quantized.astype(float)+origin-p,axis=1).max(initial=0))
    if quantization>min(.001,sampled_limit_mm):raise ValueError('shared float32 frame is too imprecise')
    pp=[];tt=[];mm=[];leaves=[];splits=[];offset=0
    def emit(ids,material,points,faces,depth,trials,operation):
        nonlocal offset
        pp.append(points);tt.append(faces+offset);offset+=len(points);mm.extend([material]*len(faces));leaves.append({'material_id':int(material),'depth':depth,'operation':operation,'input_triangle_indices':ids.tolist(),'input_triangles':len(ids),'output_triangles':len(faces),'locked_boundary_vertices':len(_border_positions(q,qt[ids])),'trials':trials})
    def visit(ids,material,depth):
        old=qt[ids];border=_border_positions(q,old);trials=[]
        def attempt(metric):
            local,faces,error=simplify_mesh(q,old,metric,lock_borders=True)
            if not _contains_positions(local,border):
                trials.append({'requested_error_mm':metric,'triangles':len(faces),'accepted':False,'reason':'locked boundary vertex missing'});return None
            points=local.astype(float)+origin
            measured=deviation(p,t[ids],points,faces,count=sample_count)
            accepted=measured['max']<=sampled_limit_mm
            trials.append({'requested_error_mm':metric,'meshoptimizer_error_mm':error,'triangles':len(faces),'sampled_deviation_mm':measured,'accepted':accepted})
            return (points,faces) if accepted else None
        candidate=attempt(error_mm)
        if candidate is not None:
            emit(ids,material,*candidate,depth,trials,'local-lod');return
        centroids=p[t[ids]].mean(1);axis=int(np.argmax(np.ptp(centroids,axis=0)))
        if depth<maximum_depth and len(ids)>=2*minimum_patch_triangles and np.ptp(centroids[:,axis])>1e-6:
            order=np.argsort(centroids[:,axis],kind='stable');mid=len(ids)//2
            splits.append({'material_id':int(material),'depth':depth,'axis':axis,'input_triangles':len(ids),'failed_trials':trials})
            visit(ids[order[:mid]],material,depth+1);visit(ids[order[mid:]],material,depth+1);return
        for refinement in range(1,5):
            candidate=attempt(error_mm/2**refinement)
            if candidate is not None:
                emit(ids,material,*candidate,depth,trials,'leaf-refinement');return
        used,inv=np.unique(qt[ids],return_inverse=True)
        # Keep the same shared numeric frame even on a conservative fallback.
        # No triangle is collapsed; movement is bounded by input quantization.
        emit(ids,material,q[used].astype(float)+origin,inv.reshape(-1,3),depth,trials,'retain-quantized-input')
    for material in np.unique(m):visit(np.flatnonzero(m==material),material,0)
    result_p=np.concatenate(pp);result_t=np.concatenate(tt);result_m=np.asarray(mm,dtype=m.dtype)
    membership=np.concatenate([leaf['input_triangle_indices'] for leaf in leaves])
    if not np.array_equal(np.sort(membership),np.arange(len(t))):raise ValueError('adaptive patches lost or duplicated input triangles')
    return result_p,result_t,result_m,{'pass':'adaptive-material-spatial-lod-v1','error_mm':error_mm,'sampled_limit_mm':sampled_limit_mm,'maximum_depth':maximum_depth,'minimum_patch_triangles':minimum_patch_triangles,'shared_origin_mm':origin.tolist(),'maximum_input_quantization_mm':quantization,'locked_patch_borders':True,'leaves':leaves,'splits':splits,'scope':'Sample-checked local tessellation LOD in one shared numeric frame; source membership is regional. No continuous error, native topology or motion equivalence claim.'}


def guarded_vertex_lod(points_mm, triangles, material_ids, *, error_mm=.25,
                       sampled_limit_mm=1, sample_count=8192,
                       maximum_iterations=12, protected_vertex_indices=()):
    """Lock failing source neighborhoods instead of refining an entire material.

    Each material trial starts from its original input mesh at the same nominal
    metric. Source triangles with failing sample points have their corners locked.
    Candidate samples too far from the source lock the nearest source
    vertices and their incident triangles. New constraints accumulate deterministically; the sampled guard is
    never increased. The component-retaining backend and material borders remain
    enabled. Optional protected vertex indices address the original input and are
    locked from the first trial. A stalled/unresolved region falls back to its unchanged input.
    """
    from scipy.spatial import cKDTree
    from mesh_quality import distances,nondegenerate
    from simplify_package import simplify_mesh
    p=np.asarray(points_mm,float);t=np.asarray(triangles);m=np.asarray(material_ids)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or m.shape!=(len(t),) or not np.issubdtype(m.dtype,np.integer):raise ValueError('invalid vertex-guard mesh')
    if not all(math.isfinite(v) and v>0 for v in (error_mm,sampled_limit_mm)) or type(sample_count) is not int or not 96<=sample_count<=262144 or type(maximum_iterations) is not int or not 1<=maximum_iterations<=32:raise ValueError('invalid vertex-guard policy')
    protected=np.asarray(protected_vertex_indices)
    if protected.ndim!=1 or (len(protected) and (not np.issubdtype(protected.dtype,np.integer) or protected.min()<0 or protected.max()>=len(p))):raise ValueError('invalid protected source vertices')
    protected=set(map(int,protected))
    origin=(p.min(0)+p.max(0))/2;quantized=np.asarray(p-origin,dtype=np.float32);quantization=float(np.linalg.norm(quantized.astype(float)+origin-p,axis=1).max(initial=0))
    if quantization>min(.001,sampled_limit_mm):raise ValueError('input too wide for float32 LOD')
    admission_limit=sampled_limit_mm-4*quantization
    if admission_limit<=0:raise ValueError('insufficient precision for sampled guard')
    pp=[];tt=[];mm=[];regions=[];offset=0
    def samples(points,faces):
        faces=nondegenerate(points,faces)
        chosen=faces[np.linspace(0,len(faces)-1,min(sample_count,len(faces)),dtype=int)]
        xyz=points[chosen]
        return np.concatenate([xyz.mean(1),xyz[:,0],(xyz[:,0]+xyz[:,1])/2]),np.tile(chosen,(3,1))
    for key in np.unique(m):
        ids=np.flatnonzero(m==key);used,inv=np.unique(t[ids],return_inverse=True);before=p[used];old=inv.reshape(-1,3);local=quantized[used];locks={i for i,v in enumerate(used) if int(v) in protected};initial_locks=len(locks);trials=[];accepted=False;tree=cKDTree(before);source_samples,source_owners=samples(before,old)
        if not len(source_samples):raise ValueError('material region has no finite-area triangles')
        for iteration in range(maximum_iterations):
            kwargs={'locked_vertex_indices':np.array(sorted(locks),dtype=np.int64)} if locks else {}
            q,faces,error=simplify_mesh(local,old,error_mm,lock_borders=True,**kwargs);points=q.astype(float)+origin
            target_samples,_=samples(points,faces)
            if not len(target_samples):raise ValueError('candidate has no finite-area triangles')
            forward=distances(source_samples,points,faces);reverse=distances(target_samples,before,old);values=np.r_[forward,reverse];bad_source=forward>admission_limit;bad_target=reverse>admission_limit;worst=float(values.max());trials.append({'iteration':iteration,'locked_vertices':len(locks),'triangles':len(faces),'meshoptimizer_error_mm':error,'sampled_deviation_mm':{'sample_count':len(values),'max':worst,'p99':float(np.percentile(values,99))},'failing_source_samples':int(bad_source.sum()),'failing_candidate_samples':int(bad_target.sum())})
            if worst<=admission_limit:accepted=True;break
            more=set(map(int,source_owners[bad_source].ravel()))
            if bad_target.any():
                nearest=np.unique(np.asarray(tree.query(target_samples[bad_target],k=min(32,len(before)))[1]).ravel())
                more.update(map(int,old[np.isin(old,nearest).any(axis=1)].ravel()))
            previous=len(locks);locks.update(more)
            if len(locks)==previous:break
        if not accepted:points=before;faces=old
        pp.append(points);tt.append(faces+offset);offset+=len(points);mm.extend([key]*len(faces));regions.append({'material_id':int(key),'input_triangles':len(old),'initial_protected_vertices':initial_locks,'output_triangles':len(faces),'operation':'guarded-vertex-lod' if accepted else 'retain-input','trials':trials,'locked_source_vertex_indices':used[np.array(sorted(locks),dtype=np.int64)].tolist(),'input_triangle_indices':ids.tolist()})
    return np.concatenate(pp),np.concatenate(tt),np.asarray(mm,dtype=m.dtype),{'pass':'sample-guarded-vertex-lock-lod-v1','error_mm':error_mm,'sampled_limit_mm':sampled_limit_mm,'admission_limit_mm':admission_limit,'maximum_iterations':maximum_iterations,'protected_source_vertex_indices':sorted(protected),'maximum_input_quantization_mm':quantization,'shared_origin_mm':origin.tolist(),'regions':regions,'scope':'Source tessellation unchanged; approximate component-retaining LOD with material borders and locally accumulated vertex locks. Deterministic samples, not a continuous error certificate.'}


def planar_outline_vertices(shape, *, minimum_face_area_mm2=5000,
                            minimum_opening_width_mm=17, corner_turn_rad=0):
    """Select native corners of broad planar outlines and larger apertures.

    Native outer wires are always included on selected faces. An inner wire is
    skipped only when its complete native width bound is strictly below the
    opening threshold. Returned vertices are selection evidence, not a declaration
    of motion ownership or permission to remove every smaller feature. Source
    faces, curves and trims are never modified.
    """
    from cad_detail_passes import area
    from cad_surface_lods import wire_width_bound_mm
    from cad_wall_fill import shape_map
    from OCP.TopAbs import TopAbs_FACE,TopAbs_WIRE,TopAbs_VERTEX,TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
    from OCP.BRepTools import BRepTools
    from OCP.BRep import BRep_Tool
    from OCP.GeomAbs import GeomAbs_Plane
    if not all(math.isfinite(v) and v>0 for v in (minimum_face_area_mm2,minimum_opening_width_mm)):raise ValueError('invalid native outline policy')
    if not math.isfinite(corner_turn_rad) or not 0<=corner_turn_rad<math.pi/2:raise ValueError('invalid corner turn')
    faces=shape_map(shape,TopAbs_FACE);points=[];records=[]
    for i in range(1,faces.Extent()+1):
        face=TopoDS.Face(faces.FindKey(i));surface=BRepAdaptor_Surface(face)
        if surface.GetType()!=GeomAbs_Plane or area(face)<minimum_face_area_mm2:continue
        ww=shape_map(face,TopAbs_WIRE);outer=BRepTools.OuterWire_s(face)
        for j in range(1,ww.Extent()+1):
            wire=TopoDS.Wire(ww.FindKey(j));is_outer=wire.IsSame(outer);width=None if is_outer else wire_width_bound_mm(face,wire)
            if width is not None and width<minimum_opening_width_mm:continue
            vv=shape_map(wire,TopAbs_VERTEX);ee=shape_map(wire,TopAbs_EDGE);all_points=[];keep=[]
            for k in range(1,vv.Extent()+1):
                vertex=TopoDS.Vertex(vv.FindKey(k));point=BRep_Tool.Pnt_s(vertex);all_points.append([point.X(),point.Y(),point.Z()]);tangents=[]
                if corner_turn_rad>0:
                    for edge_index in range(1,ee.Extent()+1):
                        edge=TopoDS.Edge(ee.FindKey(edge_index))
                        if not shape_map(edge,TopAbs_VERTEX).Contains(vertex):continue
                        curve=BRepAdaptor_Curve(edge);u=curve.FirstParameter();v=curve.LastParameter();start=curve.Value(u);end=curve.Value(v);param=u if start.Distance(point)<=end.Distance(point) else v
                        from OCP.gp import gp_Pnt,gp_Vec
                        value=gp_Pnt();tangent=gp_Vec();curve.D1(param,value,tangent);direction=np.array([tangent.X(),tangent.Y(),tangent.Z()]);length=np.linalg.norm(direction)
                        if length>1e-12:tangents.append(direction/length)
                if corner_turn_rad==0 or len(tangents)!=2 or math.acos(float(np.clip(abs(tangents[0]@tangents[1]),0,1)))>=corner_turn_rad:keep.append(k-1)
            xyz=np.asarray(all_points);extent=np.ptp(xyz,axis=0)
            if corner_turn_rad>0:
                for dim in range(3):
                    if extent[dim]>1e-6:keep.extend([int(np.argmin(xyz[:,dim])),int(np.argmax(xyz[:,dim]))])
            keep=sorted(set(keep));first=len(points);points.extend(xyz[keep].tolist());records.append({'native_face_index':i,'native_wire_index':j,'outer_wire':is_outer,'width_upper_bound_mm':width,'native_vertices':vv.Extent(),'selected_vertices':len(keep),'point_indices':list(range(first,len(points)))})
    return np.asarray(points,float).reshape(-1,3),{'pass':'broad-native-planar-outline-selection-v1','minimum_face_area_mm2':minimum_face_area_mm2,'minimum_opening_width_mm':minimum_opening_width_mm,'corner_turn_rad':corner_turn_rad,'wires':records,'scope':'Source-native corner selection only; no geometry edits or continuous between-corner preservation claim.'}
