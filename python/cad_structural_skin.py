# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-owned structural LOD with explicit geometric and optical boundaries.

The caller supplies an edited source tessellation and reviewed native outlines.
Appearance alone never authorizes a structural role. Material boundaries and
component retention remain active even when a source material is unstyled.
"""
import math
import numpy as np
from cad_planar_shell import planar_skin
from cad_local_lod import guarded_vertex_lod
from mesh_quality import deviation


def structural_skin(points_mm, triangles, material_ids, *, outline_points_mm=(),
                    protected_material_ids=(), nominal_error_mm=1,
                    sampled_limit_mm=3, sample_count=16384):
    """Reduce one explicitly selected shell from source, preserving paint seams.

    Coplanar connected regions use boundary skins. Optical/protected triangles
    are restored from original doubles. All attempts use the same source; a
    failed final distance check retains the planar or original source mesh.
    Distances are finite samples, not continuous native-surface certificates.
    """
    from scipy.spatial import cKDTree
    p=np.asarray(points_mm,float);t=np.asarray(triangles);m=np.asarray(material_ids)
    if not all(math.isfinite(v) and v>0 for v in [nominal_error_mm,sampled_limit_mm]):raise ValueError('invalid structural detail budget')
    p1,t1,m1,skin=planar_skin(p,t,m,protected_material_ids=protected_material_ids)
    locks=set(np.unique(t1[np.isin(m1,protected_material_ids)]).tolist())
    outline=np.asarray(outline_points_mm,float).reshape(-1,3)
    if len(outline):
        tree=cKDTree(p1);distance,nearest=tree.query(outline);locks.update(map(int,nearest[distance<=.01]))
        for point in outline[distance>.01]:locks.update(map(int,np.atleast_1d(tree.query(point,k=min(8,len(p1)))[1])))
    attempts=[]
    for metric in [nominal_error_mm,nominal_error_mm/2,nominal_error_mm/4]:
        q,f,k,guard=guarded_vertex_lod(p1,t1,m1,error_mm=metric,sampled_limit_mm=sampled_limit_mm,sample_count=min(sample_count,16384),maximum_iterations=8,protected_vertex_indices=np.array(sorted(locks),dtype=np.int64))
        keep=~np.isin(k,protected_material_ids);restore=np.isin(m,protected_material_ids)
        f=np.concatenate([f[keep],t[restore]+len(q)]);k=np.r_[k[keep],m[restore]];q=np.concatenate([q,p])
        quality=deviation(p,t,q,f,count=sample_count)
        attempts.append({'nominal_error_mm':metric,'triangles':len(f),'sampled_deviation_mm':quality})
        if quality['max']<=sampled_limit_mm+.001:break
    else:q,f,k=p1,t1,m1
    quality=deviation(p,t,q,f,count=sample_count)
    if quality['max']>sampled_limit_mm+.001 or len(f)>len(t):q,f,k=p,t,m;quality=deviation(p,t,q,f,count=sample_count)
    for key in protected_material_ids:
        if sorted(map(tuple,p[t[m==key]].reshape(-1,9)))!=sorted(map(tuple,q[f[k==key]].reshape(-1,9))):raise ValueError('protected structural region changed')
    return q,f,k,{'input_triangles':len(t),'planar_triangles':len(t1),'after_triangles':len(f),'sampled_limit_mm':sampled_limit_mm,'nominal_error_mm':nominal_error_mm,'sampled_deviation_mm':quality,'outline_samples':len(outline),'protected_material_ids':list(map(int,protected_material_ids)),'attempts':attempts,'scope':'Explicit shell geometry LOD, source-native outline locks and material seams. No source holes/components intentionally removed; geometry starts from edited source, not earlier approximation.'}
