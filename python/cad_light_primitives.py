# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Caller-selected light primitives with explicit fit and hidden-overlap scope.

These approximate visual surfaces never replace gameplay detectors or colliders.
A rectangle can extend inside an opaque bezel, but the caller must check exposed
color and occlusion in the complete assembly. A fitted sphere is clipped before
its hidden rear can emerge through the other side of its housing.
"""
import math
import numpy as np


def rectangle_cover(points_mm, outward_normal, *, inset_mm=0., padding_mm=0.):
    """Cover a finite planar point set with two oriented triangles.

    Minimum-area calipers follow its projected convex hull. Positive inset moves
    inward along the negative supplied outward normal. This is an enclosing
    rectangle, not an exact trim reconstruction or a proof of hidden overlap.
    """
    from scipy.spatial import ConvexHull
    p=np.asarray(points_mm,float);n=np.asarray(outward_normal,float)
    if p.ndim!=2 or p.shape[1]!=3 or len(p)<3 or not np.isfinite(p).all() or n.shape!=(3,) or not np.isfinite(n).all() or np.linalg.norm(n)<1e-12 or not all(math.isfinite(v) and v>=0 for v in (inset_mm,padding_mm)):raise ValueError('invalid planar light cover')
    n=n/np.linalg.norm(n);origin=p.mean(0);seed=np.eye(3)[np.argmin(abs(n))];x=np.cross(seed,n);x/=np.linalg.norm(x);y=np.cross(n,x);frame=np.array([x,y]);uv=(p-origin)@frame.T
    residual=float(abs((p-origin)@n).max())
    if residual>1e-4:raise ValueError('light cover source is not planar')
    hull=ConvexHull(uv);outline=uv[hull.vertices];best=None
    for edge in np.roll(outline,-1,axis=0)-outline:
        length=np.linalg.norm(edge)
        if length<1e-12:continue
        a=edge/length;b=np.array([-a[1],a[0]]);axes=np.array([a,b]);local=uv@axes.T;lo=local.min(0)-padding_mm;hi=local.max(0)+padding_mm;size=hi-lo;area=float(size.prod())
        if best is None or area<best[0]:best=(area,axes,lo,hi)
    if best is None or best[0]<1e-12:raise ValueError('degenerate light cover')
    area,axes,lo,hi=best;u0,v0=lo;u1,v1=hi;corners=np.array([[u0,v0],[u1,v0],[u1,v1],[u0,v1]])@axes@frame+origin-n*inset_mm
    return corners,np.array([[0,1,2],[0,2,3]],dtype=np.uint32),{'pass':'planar-light-cover-v1','outward_normal':n.tolist(),'inset_mm':inset_mm,'padding_mm':padding_mm,'plane_fit_residual_mm':residual,'rectangle_area_mm2':area,'projected_hull_area_mm2':float(hull.volume),'scope':'Enclosing visual quad. Extra area must be hidden or reviewed; no implicit solid/collision guarantee.'}


def fit_sphere(points_mm, *, maximum_residual_mm=1e-5):
    """Fit a sphere to source vertices with a finite residual rejection policy."""
    p=np.asarray(points_mm,float)
    if p.ndim!=2 or p.shape[1]!=3 or len(p)<4 or not np.isfinite(p).all() or not math.isfinite(maximum_residual_mm) or maximum_residual_mm<=0:raise ValueError('invalid sphere fit')
    origin=p.mean(0);q=p-origin;a=np.c_[2*q,np.ones(len(q))];solution,_,rank,_=np.linalg.lstsq(a,np.sum(q*q,axis=1),rcond=None)
    if rank<4 or solution[3]+solution[:3]@solution[:3]<=0:raise ValueError('underdetermined sphere fit')
    center=origin+solution[:3];radius=float(np.sqrt(solution[3]+solution[:3]@solution[:3]));residual=float(abs(np.linalg.norm(p-center,axis=1)-radius).max())
    if residual>maximum_residual_mm:raise ValueError('source vertices fail sphere residual guard')
    return center,radius,{'pass':'source-vertex-sphere-fit-v1','center_mm':center.tolist(),'radius_mm':radius,'maximum_vertex_radial_residual_mm':residual,'scope':'Vertex support fit, not a fit to triangle interiors or an occlusion certificate.'}


def icosphere(subdivisions):
    """Generate a unit icosphere with outward winding and 20*4**n triangles."""
    from scipy.spatial import ConvexHull
    if type(subdivisions) is not int or not 0<=subdivisions<=4:raise ValueError('icosphere subdivisions must be 0..4')
    phi=(1+math.sqrt(5))/2;v=np.array([(0,a,b*phi) for a in (-1,1) for b in (-1,1)]+[(a,b*phi,0) for a in (-1,1) for b in (-1,1)]+[(b*phi,0,a) for a in (-1,1) for b in (-1,1)],float);v/=np.linalg.norm(v,axis=1)[:,None];faces=[]
    for tri in sorted(tuple(sorted(map(int,t))) for t in ConvexHull(v).simplices):
        a,b,c=tri
        if np.dot(np.cross(v[b]-v[a],v[c]-v[a]),v[a])<0:b,c=c,b
        faces.append((a,b,c))
    points=list(v)
    for _ in range(subdivisions):
        edges={};out=[]
        def midpoint(a,b):
            key=tuple(sorted((a,b)))
            if key not in edges:
                p=(points[a]+points[b])/2;p/=np.linalg.norm(p);edges[key]=len(points);points.append(p)
            return edges[key]
        for a,b,c in faces:
            ab=midpoint(a,b);bc=midpoint(b,c);ca=midpoint(c,a);out.extend([(a,ab,ca),(b,bc,ab),(c,ca,bc),(ab,bc,ca)])
        faces=out
    return np.asarray(points),np.asarray(faces,dtype=np.uint32)


def clip_halfspace(points_mm, triangles, normal, offset_mm):
    """Clip triangles to n·p >= offset, leaving the hidden rear open.

    Cut vertices stay on their source triangle chords; they are not projected
    back onto a fitted sphere, which could push them through an opaque housing.
    """
    p=np.asarray(points_mm,float);t=np.asarray(triangles);n=np.asarray(normal,float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or n.shape!=(3,) or not np.isfinite(n).all() or np.linalg.norm(n)<1e-12 or not math.isfinite(offset_mm):raise ValueError('invalid primitive clip')
    vertices=[];faces=[];lookup={}
    def index(point):
        key=tuple(np.round(point,10))
        if key not in lookup:lookup[key]=len(vertices);vertices.append(point)
        return lookup[key]
    for tri in p[t]:
        polygon=[]
        for a,b in zip(tri,np.roll(tri,-1,axis=0)):
            da=a@n-offset_mm;db=b@n-offset_mm
            if da>=0:polygon.append(a)
            if (da>=0)!=(db>=0):polygon.append(a+(b-a)*(da/(da-db)))
        for j in range(1,len(polygon)-1):
            a,b,c=polygon[0],polygon[j],polygon[j+1]
            if np.linalg.norm(np.cross(b-a,c-a))>1e-10:faces.append([index(x) for x in (a,b,c)])
    return np.asarray(vertices).reshape(-1,3),np.asarray(faces,dtype=np.uint32).reshape(-1,3)
