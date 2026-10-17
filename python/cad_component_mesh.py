# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Shared-boundary meshing for source planar faces and extruded strips."""
from collections import defaultdict,deque
import numpy as np
from cad_component import refs
from cad_patch_matching import exact_point,scalar_args
from cad_vector_ir import VectorCurve
from cad_vector_cache import VectorCache,difference_bound


def reversed_curve(curve):
    p=curve.parameters
    if curve.kind=='line':p['endpoints_mm'].reverse()
    elif curve.kind=='source-bspline':p['reverse']=not p['reverse']
    else:raise ValueError('unsupported source curve reversal')
    return VectorCurve.make(curve.kind,p)


def translated_curve(curve,delta):
    p=curve.parameters
    key='control_points' if curve.kind=='source-bspline' else 'endpoints_mm'
    p[key]=(np.array(p[key],dtype=float)+delta).tolist()
    return VectorCurve.make(curve.kind,p)


def triangulate_polygon(points):
    """Ear-clip one simple source loop without deleting shared boundary samples."""
    points=np.asarray(points);_,_,basis=np.linalg.svd(points-points.mean(axis=0),full_matrices=False)
    q=(points-points.mean(axis=0))@basis[:2].T
    area=float(np.sum(q[:,0]*np.roll(q[:,1],-1)-q[:,1]*np.roll(q[:,0],-1)))
    if abs(area)<1e-12:raise ValueError('degenerate planar loop')
    sign=1 if area>0 else -1;remaining=list(range(len(q)));triangles=[]
    def cross(a,b):return a[:,0]*b[:,1]-a[:,1]*b[:,0]
    while len(remaining)>3:
        found=False
        for j in range(len(remaining)):
            a,b,c=remaining[j-1],remaining[j],remaining[(j+1)%len(remaining)]
            first=q[b]-q[a];second=q[c]-q[b]
            if sign*(first[0]*second[1]-first[1]*second[0])<=1e-12:continue
            other=[i for i in remaining if i not in (a,b,c)];samples=q[other]
            aa=sign*cross(np.broadcast_to(q[b]-q[a],samples.shape),samples-q[a])
            bb=sign*cross(np.broadcast_to(q[c]-q[b],samples.shape),samples-q[b])
            cc=sign*cross(np.broadcast_to(q[a]-q[c],samples.shape),samples-q[c])
            if np.any((aa>=-1e-12)&(bb>=-1e-12)&(cc>=-1e-12)):continue
            triangles.append((a,b,c));remaining.pop(j);found=True;break
        if not found:raise ValueError('cannot triangulate source loop without dropping boundary uses')
    triangles.append(tuple(remaining));return np.array(triangles,dtype=np.uint32)


def orient_closed_mesh(points,triangles):
    """Orient a connected closed triangle manifold using incidence, then volume."""
    triangles=np.array(triangles,dtype=np.uint32,copy=True);edges=defaultdict(list)
    for i,t in enumerate(triangles):
        if len(set(map(int,t)))!=3:raise ValueError('degenerate triangle ownership')
        for a,b in zip(t,np.roll(t,-1)):edges[tuple(sorted((int(a),int(b))))].append((i,int(a)<int(b)))
    if any(len(uses)!=2 for uses in edges.values()):raise ValueError('vector mesh has a boundary or nonmanifold edge')
    neighbors=defaultdict(list)
    for uses in edges.values():
        (a,sa),(b,sb)=uses;neighbors[a].append((b,sa==sb));neighbors[b].append((a,sa==sb))
    flips={0:False};todo=deque([0])
    while todo:
        a=todo.popleft()
        for b,opposite in neighbors[a]:
            value=flips[a]^opposite
            if b in flips and flips[b]!=value:raise ValueError('nonorientable vector mesh')
            if b not in flips:flips[b]=value;todo.append(b)
    if len(flips)!=len(triangles):raise ValueError('disconnected component mesh')
    for i,flip in flips.items():
        if flip:triangles[i]=triangles[i,[0,2,1]]
    local=points-points.mean(axis=0);a,b,c=local[triangles[:,0]],local[triangles[:,1]],local[triangles[:,2]]
    volume=float(np.sum(a*np.cross(b,c))/6)
    if abs(volume)<1e-9:raise ValueError('zero-volume component mesh')
    if volume<0:triangles=triangles[:,[0,2,1]];volume=-volume
    return triangles,volume


def vector_component_mesh(component,tolerance_mm=.1,*,cache=None):
    """Mesh a complete supported solid with one sample network for all faces.

    Only planar single-loop faces and source linear-extrusion strips are admitted.
    Profile pairing needs a complete polynomial translation bound, not samples.
    Native source/support deviations are checked separately by the exporter.
    """
    if not np.isfinite(tolerance_mm) or tolerance_mm<1e-4:raise ValueError('invalid component mesh tolerance')
    graph=component.graph;cache=cache or VectorCache();curves={};uses={};parameters={}
    for edge,record in graph['edges'].items():
        curves[edge]=VectorCurve.make(record['geometry']['kind'],record['geometry']['parameters']);uses[edge]=cache.register(curves[edge])
        parameters[edge]=cache.sample(uses[edge],tolerance_mm/4)[0]
    strips={};maximum_pair=0.
    for face in graph['faces']:
        if len(face['loops'])!=1:raise ValueError('component mesher does not support holes')
        surface=graph['surfaces'][face['source_surface_id']]
        if surface['kind']=='PLANE':continue
        ix=component.document.index;vector=surface['source_reference_ids'][1]
        axis=np.array(exact_point(ix,refs(ix,vector)[0]),dtype=float);axis/=np.linalg.norm(axis)
        loop=face['loops'][0]['uses'];transverse=[]
        for i,use in enumerate(loop):
            edge=use['source_edge_id'];a,b=curves[edge].evaluator().value([0,1]);d=b-a
            if curves[edge].kind=='line' and np.linalg.norm(np.cross(d,axis))<=min(.001,tolerance_mm/20):transverse.append(i)
        if len(transverse)!=2:raise ValueError('extrusion face does not have two transverse boundary edges')
        ia,ib=transverse;first=loop[ia+1:ib];second=loop[ib+1:]+loop[:ia]
        second=[{**use,'forward':not use['forward']} for use in reversed(second)]
        if len(first)!=len(second) or not first:raise ValueError('extrusion profile chains disagree')
        pairs=[]
        for a,b in zip(first,second):
            ga=curves[a['source_edge_id']];gb=curves[b['source_edge_id']]
            if not a['forward']:ga=reversed_curve(ga)
            if not b['forward']:gb=reversed_curve(gb)
            delta=gb.evaluator().value([0])[0]-ga.evaluator().value([0])[0]
            error=difference_bound(ga,translated_curve(gb,-delta))+1e-8
            if error>min(.001,tolerance_mm/20) or np.linalg.norm(np.cross(delta,axis))>min(.001,tolerance_mm/20):raise ValueError(f'source extrusion profile translation not verified: {error}')
            maximum_pair=max(maximum_pair,error);pairs.append((a,b))
            pa=parameters[a['source_edge_id']];pb=parameters[b['source_edge_id']]
            pa=pa if a['forward'] else 1-pa;pb=pb if b['forward'] else 1-pb
            raw=np.unique(np.r_[pa,pb]);shared=[float(raw[0])]
            eva,evb=ga.evaluator(),gb.evaluator()
            for parameter in raw[1:]:
                previous=shared[-1];close=True
                for evaluator in (eva,evb):
                    distance=float(np.linalg.norm(evaluator.value([parameter])[0]-evaluator.value([previous])[0]))
                    cuts=np.unique(np.r_[previous,evaluator.breaks[(evaluator.breaks>previous)&(evaluator.breaks<parameter)],parameter])
                    curvature=max((evaluator.second_bound(x,y) for x,y in zip(cuts,cuts[1:])),default=0.)
                    if distance+curvature*(parameter-previous)**2/8>1e-7:close=False;break
                if close:
                    if parameter==1:shared[-1]=1.
                else:shared.append(float(parameter))
            shared=np.array(shared)
            parameters[a['source_edge_id']]=shared if a['forward'] else 1-shared[::-1]
            parameters[b['source_edge_id']]=shared if b['forward'] else 1-shared[::-1]
        strips[face['source_face_id']]=pairs
    positions=[];indices={};edge_nodes={};source_endpoints=0.
    def vertex(key,p):
        if key not in indices:indices[key]=len(positions);positions.append(np.array(p))
        elif np.linalg.norm(positions[indices[key]]-p)>1e-5:raise ValueError('shared vector boundary mismatch')
        return indices[key]
    for edge,record in graph['edges'].items():
        use=uses[edge];t=parameters[edge];local=cache.prototypes[use.prototype].evaluator().value(t);points=local@use.rotation.T+use.origin
        ids=record['vertex_ids'];ends=np.array([graph['vertices_mm'][v] for v in ids]);raw=curves[edge].evaluator().value([0,1])
        source_endpoints=max(source_endpoints,float(np.linalg.norm(raw-ends,axis=1).max()));points[[0,-1]]=ends
        edge_nodes[edge]=[vertex(('vertex',ids[0]) if i==0 else ('vertex',ids[1]) if i==len(t)-1 else ('edge',edge,i),p) for i,p in enumerate(points)]
    triangles=[];face_ids=[]
    for face in graph['faces']:
        source=face['source_face_id'];start=len(triangles)
        if source in strips:
            for a,b in strips[source]:
                aa=edge_nodes[a['source_edge_id']];bb=edge_nodes[b['source_edge_id']]
                if not a['forward']:aa=aa[::-1]
                if not b['forward']:bb=bb[::-1]
                if len(aa)!=len(bb):raise ValueError('paired extrusion sampling changed')
                for i in range(len(aa)-1):triangles.extend(((aa[i],aa[i+1],bb[i]),(bb[i],aa[i+1],bb[i+1])))
        else:
            nodes=[]
            for use in face['loops'][0]['uses']:
                sequence=edge_nodes[use['source_edge_id']]
                if not use['forward']:sequence=sequence[::-1]
                if nodes and nodes[-1]!=sequence[0]:raise ValueError('open planar source boundary')
                nodes.extend(sequence if not nodes else sequence[1:])
            if nodes[-1]!=nodes[0]:raise ValueError('unclosed planar source boundary')
            nodes.pop();pts=np.array([positions[i] for i in nodes])
            try:local=triangulate_polygon(pts)
            except ValueError as error:raise ValueError(f'source face {source}, {len(pts)} vertices, shortest segment {np.linalg.norm(np.roll(pts,-1,axis=0)-pts,axis=1).min()}: {error}') from error
            triangles.extend(tuple(nodes[i] for i in tri) for tri in local)
        face_ids.extend([source]*(len(triangles)-start))
    points=np.array(positions);triangles,volume=orient_closed_mesh(points,np.array(triangles))
    return points,triangles,np.array(face_ids),{'faces':len(graph['faces']),'source_edges':len(edge_nodes),
        'shared_boundary_uses':sum(len(e['owners']) for e in graph['edges'].values()),'unique_boundary_samples':len(points),
        'triangles':len(triangles),'volume_mm3':volume,'closed_oriented_manifold':True,'max_profile_pair_translation_bound_mm':maximum_pair,
        'max_source_endpoint_discrepancy_mm':source_endpoints,'requested_quality_mm':tolerance_mm,'vector_cache':cache.statistics(),
        'scope':'source plane/extrusion surfaces with shared vector boundaries; source face deviation validated separately'}
