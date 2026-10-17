# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explicitly directional visual skin selection, never a collision/solid proxy.

Callers authorize the viewing envelope and supply source-scoped unit identities.
Raster invisibility is a finite diagnostic, not proof of geometric containment.
"""
import math
import struct
import subprocess
from pathlib import Path
import numpy as np


def hemisphere_views(front, angles_deg=(30,60,80), azimuth_count=8):
    """Return a front view and rings strictly inside its outward hemisphere."""
    f=np.asarray(front,float)
    if f.shape!=(3,) or not np.isfinite(f).all() or np.linalg.norm(f)<1e-12:raise ValueError('invalid front direction')
    if type(azimuth_count) is not int or azimuth_count<3 or any(not math.isfinite(a) or not 0<a<90 for a in angles_deg):raise ValueError('invalid directional envelope')
    f=f/np.linalg.norm(f);seed=np.eye(3)[np.argmin(abs(f))];u=np.cross(f,seed);u/=np.linalg.norm(u);v=np.cross(f,u)
    views=[f]
    for angle in angles_deg:
        a=math.radians(angle)
        for i in range(azimuth_count):
            b=2*math.pi*i/azimuth_count;views.append(math.cos(a)*f+math.sin(a)*(math.cos(b)*u+math.sin(b)*v))
    return np.asarray(views)


def raster_owners(geometry, view, helper, temporary_directory, *, resolution=2048):
    """Return triangle owners from a two-sided orthographic depth diagnostic.

    ``geometry`` is M×3×3 in any consistent length unit. No backface culling is
    performed by the supplied repository visibility-raster helper. Its process
    consumes only generated temporary files; source data is never modified.
    """
    g=np.asarray(geometry,float);f=np.array(view,dtype=float,copy=True)
    if g.ndim!=3 or g.shape[1:]!=(3,3) or not len(g) or not np.isfinite(g).all() or f.shape!=(3,) or not np.isfinite(f).all() or np.linalg.norm(f)<1e-12:raise ValueError('invalid visibility geometry/view')
    if type(resolution) is not int or not 64<=resolution<=4096:raise ValueError('invalid visibility resolution')
    f/=np.linalg.norm(f);seed=np.eye(3)[np.argmin(abs(f))];right=np.cross(seed,f);right/=np.linalg.norm(right);up=np.cross(f,right)
    p=g@np.column_stack((right,up,f));lo=p.min((0,1));hi=p.max((0,1));p-=(lo+hi)/2
    scale=(resolution-32)/max(hi[0]-lo[0],hi[1]-lo[1],1e-9);p[:,:,:2]*=scale;p[:,:,0]+=resolution/2;p[:,:,1]=-p[:,:,1]+resolution/2
    records=np.empty(len(g),dtype=[('p','<f4',(3,3)),('c','u1',(3,))]);records['p']=p;records['c']=128;tmp=Path(temporary_directory)
    with (tmp/'visibility-input.bin').open('wb') as stream:stream.write(struct.pack('<iii',resolution,resolution,len(g)));stream.write(records.tobytes())
    subprocess.run([str(helper),str(tmp/'visibility-input.bin'),str(tmp/'visibility.ppm'),str(tmp/'visibility-owners.bin')],check=True)
    ids=np.fromfile(tmp/'visibility-owners.bin',dtype='<i4')
    if ids.size!=resolution**2 or (ids>=len(g)).any() or (ids< -1).any():raise ValueError('invalid raster owner output')
    return np.unique(ids[ids>=0])


def directional_skin(points, triangles, material_ids, unit_ids, front, visible_triangle_ids,
                     *, rear_normal_threshold=-.02, plane_tolerance=.01):
    """Select an open-back skin and expand observations over matching planes.

    Keeps raster-observed non-rear triangles, every coplanar triangle sharing
    their native unit/material/quantized plane, and one adjacent vertex ring.
    Planes use caller length units (normally mm). Rear-facing triangles are
    excluded even if seen through an opening. Original indices, positions,
    material and native unit membership survive: no new surface is generated.
    Missing rear/interior surfaces are intentional and require caller approval.
    """
    p=np.asarray(points,float);t=np.asarray(triangles);m=np.asarray(material_ids);u=np.asarray(unit_ids);f=np.asarray(front,float);observed=np.asarray(visible_triangle_ids)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or m.shape!=(len(t),) or u.shape!=(len(t),) or not np.issubdtype(m.dtype,np.integer) or not np.issubdtype(u.dtype,np.integer):raise ValueError('invalid skin mesh')
    if f.shape!=(3,) or not np.isfinite(f).all() or np.linalg.norm(f)<1e-12 or not math.isfinite(plane_tolerance) or plane_tolerance<=0 or not math.isfinite(rear_normal_threshold) or not -1<=rear_normal_threshold<=0:raise ValueError('invalid skin policy')
    if observed.ndim!=1 or not np.issubdtype(observed.dtype,np.integer) or (len(observed) and (observed.min()<0 or observed.max()>=len(t))):raise ValueError('invalid visible triangle IDs')
    f=f/np.linalg.norm(f);g=p[t];cross=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);length=np.linalg.norm(cross,axis=1);normals=cross/np.maximum(length[:,None],1e-30);eligible=(normals@f>=rear_normal_threshold)&(length>1e-12)
    seed=np.zeros(len(t),bool);seed[observed]=True;seed&=eligible
    # Rebase the plane distance so the quantization is independent of CAD offset.
    origin=(p.min(0)+p.max(0))/2;d=np.einsum('ij,ij->i',normals,g[:,0]-origin)
    keys=np.c_[u,m,np.rint(normals/1e-5).astype(np.int64),np.rint(d/plane_tolerance).astype(np.int64)]
    _,inverse=np.unique(keys,axis=0,return_inverse=True);groups=np.unique(inverse[seed]);keep=np.isin(inverse,groups)&eligible
    # Welded geometric adjacency catches subpixel borders across duplicated mesh vertices.
    _,weld=np.unique(np.round((p-origin)/1e-5).astype(np.int64),axis=0,return_inverse=True);vertices=np.unique(weld[t[keep]])
    keep|=np.isin(weld[t],vertices).any(1)&eligible
    report={'input_triangles':len(t),'observed_triangles':len(observed),'rear_triangles':int((~eligible).sum()),'retained_triangles':int(keep.sum()),'removed_triangles':int((~keep).sum()),'removed_units':[int(k) for k in np.unique(u) if not keep[u==k].any()],'rear_normal_threshold':rear_normal_threshold,'plane_tolerance':plane_tolerance,'scope':'Directional finite-raster visual skin; open back and discarded interior, not all-view visibility proof, watertight solid or collision.'}
    return np.flatnonzero(keep),report


def all_view_skin(points, triangles, material_ids, visible_triangle_ids, *,
                  protected_material_ids=(), plane_tolerance_mm=.001):
    """Keep all observed orientations, complete coplanar patches and one edge ring.

    The caller supplies observations of **one rigid source-owned shell** from
    directions around the full sphere. No other moving member may occlude it.
    Protected materials survive in full. Retained triangles stay exact; omitted
    surfaces are only unobserved in finite raster samples, never proved hidden.
    Unlike a directional skin, this has no rear-facing rejection or open back.
    """
    p=np.asarray(points,float);t=np.asarray(triangles);m=np.asarray(material_ids)
    observed=np.asarray(visible_triangle_ids)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or m.shape!=(len(t),) or not np.issubdtype(m.dtype,np.integer):raise ValueError('invalid all-view skin mesh')
    if observed.ndim!=1 or not np.issubdtype(observed.dtype,np.integer) or not len(observed) or observed.min()<0 or observed.max()>=len(t) or not math.isfinite(plane_tolerance_mm) or plane_tolerance_mm<=0:raise ValueError('invalid all-view observations/policy')
    g=p[t];cross=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);length=np.linalg.norm(cross,axis=1)
    normal=cross/np.maximum(length[:,None],1e-30);origin=(p.min(0)+p.max(0))/2
    offsets=np.einsum('ij,ij->i',normal,g[:,0]-origin)
    keys=np.c_[m,np.rint(normal/1e-5).astype(np.int64),np.rint(offsets/plane_tolerance_mm).astype(np.int64)]
    _,groups=np.unique(keys,axis=0,return_inverse=True)
    keep=np.isin(groups,np.unique(groups[observed]))|np.isin(m,protected_material_ids)
    _,weld=np.unique(p,axis=0,return_inverse=True)
    vertices=np.unique(weld[t[keep]]);keep|=np.isin(weld[t],vertices).any(1)
    return np.flatnonzero(keep),{'pass':'all-view-shell-skin-v1','input_triangles':len(t),
        'observed_triangles':len(observed),'retained_triangles':int(keep.sum()),
        'protected_material_ids':list(map(int,protected_material_ids)),
        'plane_tolerance_mm':plane_tolerance_mm,
        'scope':'One rigid shell only; full-sphere finite-raster observations, coplanar expansion and one exact-position adjacency ring. No continuous visibility, solid, collision or animation equivalence claim.'}
