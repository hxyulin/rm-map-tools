# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Orthographic source relief maps for explicitly selected planar detail layers.

The output is an intermediate texture representation, not a reason to delete
silhouette geometry. Undercuts and side walls need separate geometry or views.
Normals use a right-handed tangent frame and linear RGB encoding, never sRGB.
"""
import numpy as np


def bake_relief(points_mm, triangles, triangle_srgb, *, origin_mm, axes,
                bounds_uv_mm, resolution=512):
    """Bake frontmost source color, tangent normal, height and coverage.

    ``axes`` rows are tangent +U, +V and view normal; bounds are u0,v0,u1,v1.
    Rows run from +V to -V, matching an ordinary top-origin image. Height is
    signed source millimetres along the view normal, relative to origin. This
    deterministic two-sided raster samples pixel centers without filtering or
    ambient occlusion. Empty pixels have zero coverage and neutral +Z normals.
    The caller owns atlas gutters, mipmaps, UV attachment and renderer validation.
    """
    p=np.asarray(points_mm,float);t=np.asarray(triangles);rgb=np.asarray(triangle_srgb,float);origin=np.asarray(origin_mm,float);frame=np.asarray(axes,float);bounds=np.asarray(bounds_uv_mm,float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not np.issubdtype(t.dtype,np.integer) or not len(t) or t.min()<0 or t.max()>=len(p) or rgb.shape!=(len(t),3) or not np.isfinite(rgb).all() or np.any((rgb<0)|(rgb>1)):
        raise ValueError('invalid relief source')
    if origin.shape!=(3,) or frame.shape!=(3,3) or bounds.shape!=(4,) or not np.isfinite(np.r_[origin,frame.ravel(),bounds]).all() or not np.allclose(frame@frame.T,np.eye(3),atol=1e-10,rtol=0) or abs(np.linalg.det(frame)-1)>1e-10 or np.any(bounds[2:]<=bounds[:2]) or type(resolution) is not int or not 16<=resolution<=4096:
        raise ValueError('invalid relief frame or resolution')
    local=(p-origin)@frame.T;projected=local.copy();scale=resolution/(bounds[2:]-bounds[:2]);projected[:,:2]=(local[:,:2]-bounds[:2])*scale;projected[:,1]=resolution-projected[:,1]
    owner=np.full((resolution,resolution),-1,dtype=np.int32);height=np.full((resolution,resolution),-np.inf);normals=np.cross(local[t[:,1]]-local[t[:,0]],local[t[:,2]]-local[t[:,0]]);lengths=np.linalg.norm(normals,axis=1);normals/=np.maximum(lengths[:,None],1e-30);normals[normals[:,2]<0]*=-1
    for i,vertices in enumerate(projected[t]):
        x0,y0=np.maximum(np.floor(vertices[:,:2].min(0)).astype(int),0);x1,y1=np.minimum(np.ceil(vertices[:,:2].max(0)).astype(int),resolution-1)
        if x0>x1 or y0>y1:continue
        a,b,c=vertices;den=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if abs(den)<1e-12 or lengths[i]<1e-20:continue
        y,x=np.mgrid[y0:y1+1,x0:x1+1];x=x+.5;y=y+.5;u=((b[0]-x)*(c[1]-y)-(b[1]-y)*(c[0]-x))/den;v=((c[0]-x)*(a[1]-y)-(c[1]-y)*(a[0]-x))/den;w=1-u-v;z=u*a[2]+v*b[2]+w*c[2];block=height[y0:y1+1,x0:x1+1];mask=(u>=-1e-10)&(v>=-1e-10)&(w>=-1e-10)&(z>block);block[mask]=z[mask];owner[y0:y1+1,x0:x1+1][mask]=i
    covered=owner>=0;base=np.zeros((resolution,resolution,4),dtype=np.uint8);normal=np.zeros((resolution,resolution,3),dtype=np.uint8);normal[:]=[128,128,255];base[covered,:3]=np.rint(rgb[owner[covered]]*255).astype(np.uint8);base[covered,3]=255;normal[covered]=np.rint((normals[owner[covered]]*.5+.5)*255).astype(np.uint8);height[~covered]=np.nan
    return {'base_colour_rgba':base,'normal_rgb_linear':normal,'height_mm':height.astype(np.float32),'source_triangle_owner':owner,
            'metadata':{'pass':'orthographic-source-relief-v1','origin_mm':origin.tolist(),'axes':frame.tolist(),'bounds_uv_mm':bounds.tolist(),'resolution':resolution,'normal_convention':'right-handed tangent XYZ, +V up, linear RGB; top image row is +V','height_units':'mm relative to source origin along normal','coverage_fraction':float(covered.mean()),'height_min_mm':float(height[covered].min()) if covered.any() else None,'height_max_mm':float(height[covered].max()) if covered.any() else None,'scope':'Source projection only. Not an AO bake or an automatic mesh replacement; silhouettes and undercuts remain geometry.'}}
