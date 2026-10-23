# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Boundary-constrained retriangulation of selected cylindrical structure patches.

Unwrap onto a native cylinder, union source triangle domains and triangulate
angular sectors. Open/recess boundary loops remain explicit; no hull or compact
piece deletion is used. Output is inspection-only.
"""
import numpy as np
import shapely
from shapely.geometry import Polygon,box,Point
from shapely.strtree import STRtree
from scipy.spatial import cKDTree
from cad_dense_lod import surface_samples
from mesh_quality import distances

def frame(axis):
 a=np.asarray(axis,float);a/=np.linalg.norm(a);u=np.cross(a,np.eye(3)[np.argmin(abs(a))]);u/=np.linalg.norm(u);v=np.cross(a,u);return a,u,v

def select(g,axis,anchor,lo,hi,rmin):
 a,u,v=frame(axis);x=np.asarray(g)-anchor;h=x@a;r=np.hypot(x@u,x@v)
 return (h.min(1)>=lo-.002)&(h.max(1)<=hi+.002)&(r.min(1)>=rmin)&(np.ptp(h,axis=1)>.005)

def samples(g,level=2):
 for _ in range(level):
  a,b,c=g[:,0],g[:,1],g[:,2];ab=(a+b)/2;bc=(b+c)/2;ca=(c+a)/2
  g=np.concatenate([np.stack([a,ab,ca],1),np.stack([ab,b,bc],1),np.stack([ca,bc,c],1),np.stack([ab,bc,ca],1)])
 return surface_samples(g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3)).reshape(-1,3)

def measure(old,new,level=2):
 f=distances(samples(old,level),new.reshape(-1,3),np.arange(len(new)*3).reshape(-1,3));b=distances(samples(new,level),old.reshape(-1,3),np.arange(len(old)*3).reshape(-1,3))
 return {'source_to_output_mm':float(f.max(initial=0)),'output_to_source_mm':float(b.max(initial=0)),'max_mm':float(max(f.max(initial=0),b.max(initial=0))),'samples':len(f)+len(b),'subdivision_levels':level}

def retriangulate(g,*,axis,anchor,radius,sectors):
 a,u,v=frame(axis);x=g-anchor;ang=np.arctan2(x@v,x@u);h=x@a;uvpolys=[];orig=[]
 for j in range(len(g)):
  t=ang[j].copy()
  if np.ptp(t)>np.pi:t[t<0]+=2*np.pi
  uv=np.c_[t*radius,h[j]]
  if abs(np.linalg.det(np.c_[uv[1]-uv[0],uv[2]-uv[0]]))<1e-10:continue
  for offset in [-2*np.pi*radius,0,2*np.pi*radius]:
   z=uv+[offset,0]
   if z[:,0].max()<-np.pi*radius or z[:,0].min()>np.pi*radius:continue
   uvpolys.append(Polygon(z));orig.append((z,g[j]))
 dom=shapely.union_all(shapely.set_precision(uvpolys,.000001));tree=STRtree(uvpolys)
 vertices=np.concatenate([z for z,_ in orig]);positions=np.concatenate([p for _,p in orig]);kdt=cKDTree(vertices)
 def lift(q):
  dd,ii=kdt.query(q)
  if dd<.00001:return positions[ii]
  for j in tree.query(Point(q).buffer(.00002)):
   uv,p=orig[j];weights=np.linalg.solve(np.c_[uv[1]-uv[0],uv[2]-uv[0]],q-uv[0]);weights=np.r_[1-weights.sum(),weights]
   if weights.min()>-.0001 and weights.max()<1.0001:return weights@p
  raise ValueError('unmapped parameter vertex')
 result=[];ranges=np.linspace(-np.pi*radius,np.pi*radius,sectors+1)
 for lo,hi in zip(ranges,ranges[1:]):
  clipped=dom.intersection(box(lo,-1e6,hi,1e6))
  for poly in shapely.get_parts(clipped):
   if poly.geom_type!='Polygon':continue
   tris=shapely.constrained_delaunay_triangles(poly)
   for tri in shapely.get_parts(tris):
    uv=np.asarray(tri.exterior.coords)[:3];pts=np.array([lift(q) for q in uv]);center=pts.mean(0)-anchor;radial=center-a*(center@a)
    # Match the source surface orientation by nearest source triangle normal.
    nearest=np.argmin(np.linalg.norm(g.mean(1)-pts.mean(0),axis=1));sn=np.cross(g[nearest,1]-g[nearest,0],g[nearest,2]-g[nearest,0])
    if np.dot(np.cross(pts[1]-pts[0],pts[2]-pts[0]),sn)<0:pts=pts[::-1]
    result.append(pts)
 out=np.array(result).reshape(-1,3,3)
 return out,{'sectors':sectors,'maximum_angular_span_rad':2*np.pi/sectors,'circular_sagitta_mm':float(radius*(1-np.cos(np.pi/sectors))),'parameter_domain_area_mm2':float(dom.intersection(box(-np.pi*radius,-1e6,np.pi*radius,1e6)).area)}

def boundaries(g):
 p,inv=np.unique(np.round(g.reshape(-1,3),4),axis=0,return_inverse=True);f=inv.reshape(-1,3);edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1);e,c=np.unique(edges,axis=0,return_counts=True)
 return p[e[c==1]]

def boundary_error(old,new):
 def direction(a,b):
  if not len(a):return 0.
  if not len(b):return float('inf')
  pts=np.concatenate([a[:,0],a[:,1],a.mean(1)]);out=[]
  v=b[:,1]-b[:,0];den=np.maximum((v*v).sum(1),1e-30)
  for s in np.array_split(pts,max(1,len(pts)//256)):
   delta=s[:,None]-b[None,:,0];w=np.clip((delta*v[None]).sum(2)/den,0,1);dd=delta-w[:,:,None]*v[None];out.extend(np.sqrt((dd*dd).sum(2).min(1)))
  return float(max(out,default=0))
 a,b=boundaries(old),boundaries(new)
 return {'before_edges':len(a),'after_edges':len(b),'maximum_sampled_boundary_mm':max(direction(a,b),direction(b,a))}
