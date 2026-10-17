# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Finite, straight-boundary planar patches with explicit source correspondence.

The exact key uses rational decimal coordinates and checks source line/plane
incidence. Quantized keys only discover candidates; no CAD or mesh is changed.
Curved edges, holes and unsupported topology are explicitly refused for now.
"""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import re

import numpy as np
from cad_optimizer import TOKEN
from cad_ir_structure import PassContract

NUMBER = re.compile(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?')


def scalar_args(ix, row):
    """Numeric arguments outside strings, references and enum/identifier names."""
    text=ix.args(row)
    text=TOKEN.sub(lambda m:b'' if m.group().startswith((b"'",b'"',b'/*',b'#')) else m.group(),text)
    return NUMBER.findall(text)


def exact_point(ix, source):
    row=ix.r(source)
    if row<0 or ix.tname(row) not in ('CARTESIAN_POINT','DIRECTION'):
        raise ValueError('expected point or direction')
    values=tuple(Fraction(v.decode()) for v in scalar_args(ix,row))
    if len(values)!=3:raise ValueError('expected 3D coordinates')
    return values


def sense(ix, source):
    text=ix.text(ix.r(source))
    # Preserve literals while locating the final explicit flag.
    text=TOKEN.sub(lambda m:m.group() if m.group().startswith((b"'",b'"',b'#')) else (m.group(2) or b''),text)
    match=re.search(rb',\.(T|F)\.\);$',text)
    if match is None:raise ValueError('missing explicit orientation')
    return match.group(1)==b'T'


def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


@dataclass(frozen=True)
class PolygonPatch:
    """One source face with one ordered planar straight-edge outer loop."""
    document: object
    face_id: int
    bound_id: int
    loop_id: int
    surface_id: int
    vertex_ids: tuple
    edge_ids: tuple
    oriented_edge_ids: tuple
    points: tuple  # exact decimal Fraction triples, source length units
    orientations: tuple  # face, bound, then (oriented edge, edge curve) pairs

    def coordinates(self):
        return np.asarray(self.points,dtype=float)

    def exact_incidence(self):
        """Require exact line/plane agreement, not an inferred floating tolerance."""
        ix=self.document.index; surface=ix.refs_of(ix.r(self.surface_id))
        axis=ix.refs_of(ix.r(int(surface[0])))
        if ix.tname(ix.r(int(surface[0])))!='AXIS2_PLACEMENT_3D' or not len(axis):
            raise ValueError('unsupported plane frame')
        origin=exact_point(ix,int(axis[0])); normal=exact_point(ix,int(axis[1])) if len(axis)>=2 else (Fraction(0),Fraction(0),Fraction(1))
        if dot(normal,normal)==0:raise ValueError('zero plane normal')
        if any(dot(sub(p,origin),normal)!=0 for p in self.points):raise ValueError('inexact source plane incidence')
        for i,edge in enumerate(self.edge_ids):
            refs=ix.refs_of(ix.r(edge)); line=ix.refs_of(ix.r(int(refs[2])))
            if len(line)!=2:raise ValueError('unsupported line')
            base=exact_point(ix,int(line[0])); vector=ix.refs_of(ix.r(int(line[1])))
            if ix.tname(ix.r(int(line[1])))!='VECTOR' or len(vector)!=1:raise ValueError('unsupported line vector')
            magnitude=scalar_args(ix,ix.r(int(line[1])))
            if len(magnitude)!=1 or Fraction(magnitude[0].decode())<=0:raise ValueError('zero line magnitude')
            direction=exact_point(ix,int(vector[0]))
            if dot(direction,direction)==0:raise ValueError('zero line direction')
            for point in (self.points[i],self.points[(i+1)%len(self.points)]):
                if any(cross(sub(point,base),direction)):raise ValueError('inexact source line incidence')
        # An invalid self-intersecting trim is not a reusable finite polygon.
        drop=max(range(3),key=lambda axis:abs(normal[axis]))
        projected=[tuple(value for axis,value in enumerate(point) if axis!=drop) for point in self.points]
        def side(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        def on(a,b,p):return all(min(a[k],b[k])<=p[k]<=max(a[k],b[k]) for k in (0,1))
        for i in range(len(projected)):
            a,b=projected[i],projected[(i+1)%len(projected)]
            for j in range(i+1,len(projected)):
                if j==i+1 or (i==0 and j==len(projected)-1):continue
                c,d=projected[j],projected[(j+1)%len(projected)]
                ab_c,ab_d,cd_a,cd_b=side(a,b,c),side(a,b,d),side(c,d,a),side(c,d,b)
                if (ab_c*ab_d<0 and cd_a*cd_b<0) or any((not v and on(x,y,z)) for v,x,y,z in
                    ((ab_c,a,b,c),(ab_d,a,b,d),(cd_a,c,d,a),(cd_b,c,d,b))):
                    raise ValueError('self-intersecting polygon trim')
        # Side of the ordered loop relative to the source surface normal.
        area=tuple(sum(cross(sub(self.points[i],origin),sub(self.points[(i+1)%len(self.points)],origin))[k]
                       for i in range(len(self.points))) for k in range(3))
        sign=dot(area,normal)
        if not sign:raise ValueError('degenerate polygon')
        return 1 if sign>0 else -1


def polygon_patch(document, face_id, *, max_vertices=64):
    """Decode a simple closed source loop; reject holes, curve edges and gaps."""
    ix=document.index;row=ix.r(face_id)
    if row<0 or ix.tname(row)!='ADVANCED_FACE':raise ValueError('not an advanced face')
    refs=list(map(int,ix.refs_of(row)))
    if len(refs)!=2:raise ValueError('multiple/no bounds')
    bound,surface=refs
    if ix.tname(ix.r(surface))!='PLANE':raise ValueError('nonplanar surface')
    if ix.tname(ix.r(bound))!='FACE_OUTER_BOUND':raise ValueError('not an explicit outer bound')
    bounds=ix.refs_of(ix.r(bound))
    if len(bounds)!=1:raise ValueError('unsupported bound')
    loop=int(bounds[0]);looprow=ix.r(loop)
    if ix.tname(looprow)!='EDGE_LOOP':raise ValueError('not an edge loop')
    oriented=tuple(map(int,ix.refs_of(looprow)))
    if not 3<=len(oriented)<=max_vertices:raise ValueError('polygon size outside limit')
    vertices=[];ends=[];edges=[];flags=[sense(ix,face_id),sense(ix,bound)]
    for use in oriented:
        if ix.tname(ix.r(use))!='ORIENTED_EDGE':raise ValueError('unsupported edge use')
        ref=ix.refs_of(ix.r(use))
        if len(ref)!=1:raise ValueError('non-derived oriented edge endpoints')
        edge=int(ref[0]);refs=tuple(map(int,ix.refs_of(ix.r(edge))))
        if ix.tname(ix.r(edge))!='EDGE_CURVE' or len(refs)!=3:raise ValueError('unsupported edge curve')
        if ix.tname(ix.r(refs[2]))!='LINE':raise ValueError('curved boundary')
        forward=sense(ix,use);start,end=refs[:2] if forward else refs[1::-1]
        vertices.append(start);ends.append(end);edges.append(edge);flags.extend((forward,sense(ix,edge)))
    if any(ends[i]!=vertices[(i+1)%len(vertices)] for i in range(len(vertices))):raise ValueError('open/disconnected loop')
    points=[]
    for vertex in vertices:
        ref=ix.refs_of(ix.r(vertex))
        if ix.tname(ix.r(vertex))!='VERTEX_POINT' or len(ref)!=1:raise ValueError('unsupported vertex')
        points.append(exact_point(ix,int(ref[0])))
    if len(set(points))<3:raise ValueError('degenerate polygon')
    if any(points[i]==points[(i+1)%len(points)] for i in range(len(points))):raise ValueError('zero-length polygon edge')
    return PolygonPatch(document,face_id,bound,loop,surface,tuple(vertices),tuple(edges),oriented,tuple(points),tuple(flags))


def patch_key(patch, *, quantum=None):
    """Return cyclic-start invariant finite metric key and source ordering.

    `quantum=None` requires exact source incidence. A positive quantum in source
    length units rounds distances for discovery only, never geometry acceptance.
    Source vertex/edge alias patterns and use senses remain part of either key.
    """
    if quantum is not None and (not np.isfinite(quantum) or quantum<=0):raise ValueError('invalid discovery quantum')
    sign=patch.exact_incidence() if quantum is None else 0
    n=len(patch.points); distances={}
    for i in range(n):
        for j in range(i):
            delta=sub(patch.points[i],patch.points[j]); squared=dot(delta,delta)
            distances[i,j]=(squared.numerator,squared.denominator) if quantum is None else int(round(float(squared)**.5/quantum))
    candidates=[]
    for start in range(n):
        order=tuple((start+i)%n for i in range(n));ids={};alias=[]
        for values in (patch.vertex_ids,patch.edge_ids,patch.oriented_edge_ids):
            for i in order:
                source=values[i]
                if source not in ids:ids[source]=len(ids)
                alias.append(ids[source])
        lengths=tuple(distances[max(order[i],order[j]),min(order[i],order[j])] for i in range(n) for j in range(i))
        flags=patch.orientations[:2]+tuple(v for i in order for v in patch.orientations[2+2*i:4+2*i])
        candidates.append(((n,sign,flags,tuple(alias),lengths),order))
    key,order=min(candidates)
    digest=hashlib.sha256(json.dumps(key,separators=(',',':')).encode()).hexdigest()
    return digest,key,order


def patch_correspondence(reference, candidate, *, quantum=None):
    """Verify finite metric equality and produce explicit original-use maps.

    Approximate discovery keys yield a measured rigid-fit candidate only. No
    parameterization/material/owner equivalence or mesh edit is inferred.
    """
    if reference.document is not candidate.document:raise ValueError('patch correspondence requires one source document/context')
    _,a,oa=patch_key(reference,quantum=quantum);_,b,ob=patch_key(candidate,quantum=quantum)
    if a!=b:raise ValueError('different finite patch keys')
    source=reference.coordinates()[list(oa)];target=candidate.coordinates()[list(ob)]
    ca=source.mean(axis=0);cb=target.mean(axis=0)
    u,_,vh=np.linalg.svd((source-ca).T@(target-cb))
    rotation=vh.T@u.T
    if np.linalg.det(rotation)<0:vh[-1]*=-1;rotation=vh.T@u.T
    translation=cb-rotation@ca
    residual=np.linalg.norm(source@rotation.T+translation-target,axis=1)
    matrix=np.eye(4);matrix[:3,:3]=rotation;matrix[:3,3]=translation
    correspondence={}
    for name in ('vertex_ids','edge_ids','oriented_edge_ids'):
        left=getattr(reference,name);right=getattr(candidate,name)
        mapping=list(zip((left[i] for i in oa),(right[i] for i in ob)))
        if len(set(x for x,_ in mapping))!=len(set(y for _,y in mapping)):
            raise ValueError('non-bijective patch incidence')
        correspondence[name]=mapping
    return {'reference_face_id':reference.face_id,'candidate_face_id':candidate.face_id,
            'bound_map':[reference.bound_id,candidate.bound_id],'loop_map':[reference.loop_id,candidate.loop_id],
            'correspondence':correspondence,'reference_to_candidate_matrix_source_units':matrix.tolist(),
            'max_vertex_residual_source_units':float(residual.max()),
            'acceptance':'exact rational finite polygon congruence' if quantum is None else 'quantized discovery only; no reuse authorized'}


PATCH_CONTRACT = PassContract('finite-planar-polygons-v1',
    ('single outer EDGE_LOOP','straight LINE boundaries','one source document/context','nondegenerate simple polygon'),
    ('original face/bound/loop/edge/vertex IDs','loop order and incidence','source geometry and metadata'),
    'cyclic-start maps; exact rational line/plane incidence and finite distances; quantized keys only discover candidates',
    'finite patch groups and additional source uses; no material merge, mesh or triangle saving implied')
