# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Convex profile prisms for explicitly selected small monochrome housings.

This intentionally fills engraving, concavities and recesses. Callers must bind
source material, rigid scope and feature semantics; it is never a generic hull
replacement for an arena structure or a gameplay detector.
"""
import math
import numpy as np
from cad_collision_profiles import simplify_loop,prism_mesh
from cad_dense_lod import surface_samples
from mesh_quality import distances


def profile_envelope(points_mm,triangles,normal,*,boundary_error_mm=.5,
                     maximum_surface_distance_mm=4):
    """Extrude a convex projected source outline through its measured depth.

    Profile vertices come from the projected source convex hull, then use an
    inward chord simplification. All source and output triangle corners, edge
    midpoints and centroids are checked in both directions. Rejection leaves the
    input untouched. This finite guard does not certify a native solid, preserve
    through holes, select suitable parts or prove continuous surface error.
    """
    from scipy.spatial import ConvexHull
    p=np.asarray(points_mm,float);t=np.asarray(triangles);n=np.asarray(normal,float)
    if p.ndim!=2 or p.shape[1]!=3 or not np.isfinite(p).all() or t.ndim!=2 or t.shape[1]!=3 or not len(t) or not np.issubdtype(t.dtype,np.integer)or t.min()<0 or t.max()>=len(p):raise ValueError('invalid envelope mesh')
    if n.shape!=(3,)or not np.isfinite(n).all()or np.linalg.norm(n)<1e-12 or not all(math.isfinite(v)and v>0 for v in [boundary_error_mm,maximum_surface_distance_mm]):raise ValueError('invalid envelope policy')
    support=p[np.unique(t)];n=n/np.linalg.norm(n);seed=np.eye(3)[np.argmin(abs(n))];x=np.cross(seed,n);x/=np.linalg.norm(x);y=np.cross(n,x);origin=support.mean(0);uv=(support-origin)@np.array([x,y]).T;hull=ConvexHull(uv);outline=simplify_loop(uv[hull.vertices],boundary_error_mm);depths=(support-origin)@n;depth=float(np.ptp(depths))
    if depth<=1e-5:raise ValueError('profile has no finite depth')
    ring=origin+outline@np.array([x,y])+depths.max()*n;q,f,topology=prism_mesh([{'outer':True,'points_mm':ring}],n,depth);forward=distances(surface_samples(p,t).reshape(-1,3),q,f);reverse=distances(surface_samples(q,f).reshape(-1,3),p,t);worst=float(max(forward.max(),reverse.max()))
    if worst>maximum_surface_distance_mm:raise ValueError('profile envelope exceeds sampled surface allowance '+str(worst))
    return q,f,{'pass':'selected-convex-profile-envelope-v1','input_triangles':len(t),'output_triangles':len(f),'profile_vertices':len(ring),'depth_mm':depth,'normal':n.tolist(),'boundary_error_mm':boundary_error_mm,'maximum_sampled_distance_mm':worst,'maximum_surface_distance_mm':maximum_surface_distance_mm,'topology':topology,'scope':'Explicit monochrome housing envelope. Engraving/recesses/concavities intentionally fill; finite source-surface samples and closed mesh topology, not native-solid equality or opening preservation.'}
