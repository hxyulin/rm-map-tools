# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explicit game-detail omission inside one source-owned rigid member.

CAD exports can pack hundreds of disconnected fasteners/chips into one shell.
Connectivity here is a selection aid, not inferred solid or motion ownership.
"""
import math
import numpy as np


def connected_pieces(points_mm, triangles, *, selection_grid_mm=.01):
    """Label triangle connectivity through shared quantized vertex positions.

    Quantization affects selection only; original positions stay unchanged.
    Call separately per rigid member. Pieces touching at any shared vertex are
    conservatively joined. No near-vertex weld is written into the output.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    p=np.asarray(points_mm,float);t=np.asarray(triangles)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not len(t) or not np.issubdtype(t.dtype,np.integer) or t.min()<0 or t.max()>=len(p):raise ValueError('invalid piece mesh')
    if not math.isfinite(selection_grid_mm) or selection_grid_mm<=0:raise ValueError('invalid selection grid')
    origin=p[t].min((0,1));_,inv=np.unique(np.round((p[t].reshape(-1,3)-origin)/selection_grid_mm).astype(np.int64),axis=0,return_inverse=True);f=inv.reshape(-1,3);edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);_,labels=connected_components(coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(int(f.max())+1,)*2).tocsr(),directed=False)
    return labels[f[:,0]]


def compact_detail_filter(points_mm, triangles, material_ids, *, maximum_extent_mm=17,
                          maximum_backing_distance_mm=17, protected_material_ids=(),
                          protected_triangle_indices=(), selection_grid_mm=.01,
                          rigid_backing_mesh=None):
    """Omit compact, non-optical pieces close to a retained larger surface.

    Both limits are strict. All three world-axis extents must be below the size
    limit. Every vertex of an omitted piece must be closer than the backing
    limit to retained larger/protected geometry. Isolated pieces remain. Whole
    connected pieces are selected, never fragments cut by a spatial box. This
    deliberately discards detail; it is not a visibility or containment proof.
    Returns kept original triangle indices and a per-piece decision ledger.
    Optional ``rigid_backing_mesh=(points, triangles)`` lets the caller supply
    larger/protected surfaces in the **same certified rigid assembly**. It must
    exclude all candidate micro-pieces and every independently moving owner.
    This function does not infer or certify that assembly contract.
    """
    from mesh_quality import distances
    p=np.asarray(points_mm,float);t=np.asarray(triangles);m=np.asarray(material_ids)
    if not all(math.isfinite(v) and v>0 for v in [maximum_extent_mm,maximum_backing_distance_mm]):raise ValueError('invalid detail omission policy')
    labels=connected_pieces(p,t,selection_grid_mm=selection_grid_mm)
    if m.shape!=(len(t),) or not np.issubdtype(m.dtype,np.integer):raise ValueError('invalid material labels')
    protected=np.asarray(protected_triangle_indices)
    if protected.ndim!=1 or (len(protected)and(not np.issubdtype(protected.dtype,np.integer)or protected.min()<0 or protected.max()>=len(t))):raise ValueError('invalid protected triangles')
    protected_pieces=set(labels[protected.astype(np.int64)].tolist());candidate=[];records=[]
    for part in np.unique(labels):
        ids=np.flatnonzero(labels==part);used=np.unique(t[ids]);span=np.ptp(p[used],axis=0);optical=bool(np.isin(m[ids],protected_material_ids).any());eligible=bool(span.max()<maximum_extent_mm and not optical and part not in protected_pieces)
        records.append({'piece':int(part),'triangles':len(ids),'span_mm':span.tolist(),'protected':bool(optical or part in protected_pieces),'eligible':eligible,'removed':False})
        if eligible:candidate.append(part)
    backing=t[~np.isin(labels,candidate)];backing_points=p;keep=np.ones(len(t),bool)
    if rigid_backing_mesh is not None:
        bp,bt=rigid_backing_mesh;bp=np.asarray(bp,float);bt=np.asarray(bt)
        if bp.ndim!=2 or bp.shape[1]!=3 or not np.isfinite(bp).all() or bt.ndim!=2 or bt.shape[1]!=3 or not np.issubdtype(bt.dtype,np.integer) or (len(bt) and (bt.min()<0 or bt.max()>=len(bp))):raise ValueError('invalid rigid backing mesh')
        backing=np.concatenate([backing,bt+len(p)]);backing_points=np.concatenate([p,bp])
    if len(backing):
        vertices=np.unique(t[np.isin(labels,candidate)])
        errors=np.zeros(len(p));errors[vertices]=distances(p[vertices],backing_points,backing) if len(vertices) else []
        for record in records:
            if not record['eligible']:continue
            ids=np.flatnonzero(labels==record['piece']);error=float(errors[np.unique(t[ids])].max());record['maximum_backing_distance_mm']=error
            if error<maximum_backing_distance_mm:keep[ids]=False;record['removed']=True
    return np.flatnonzero(keep),{'pass':'source-member-compact-detail-v1','input_triangles':len(t),'output_triangles':int(keep.sum()),'maximum_extent_mm':maximum_extent_mm,'maximum_backing_distance_mm':maximum_backing_distance_mm,'selection_grid_mm':selection_grid_mm,'pieces':records,'scope':'Explicit lossy compact-detail omission inside one rigid source member. Strict size/backing limits, exact retained indices and protected optical/port pieces. Proximity is not visibility or solid containment.'}
