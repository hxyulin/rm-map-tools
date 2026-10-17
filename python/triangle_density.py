# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Count every placed triangle once in an explicit XY centroid grid.

Density describes mesh concentration, not covered area, GPU overdraw or unique
buffer storage. Vertical and occluded surfaces are counted at their XY centroid.
"""
import math
import numpy as np


def centroid_grid(triangles,*,lower_m,upper_m,cell_size_m=.5):
    """Return a Y-row/X-column count grid over a shared, closed XY envelope.

    Bounds and cell size are metres. Upper-edge centroids belong to the last
    cell; all other out-of-envelope geometry is refused, never silently dropped.
    Empty input produces an empty count grid with the same fixed extent.
    """
    triangles=np.asarray(triangles,dtype=float)
    lower=np.asarray(lower_m,dtype=float);upper=np.asarray(upper_m,dtype=float)
    if triangles.shape[-2:]!=(3,3) or triangles.ndim!=3 or not np.isfinite(triangles).all():raise ValueError('expected finite N x 3 x 3 triangle positions')
    if lower.shape!=(2,) or upper.shape!=(2,) or not np.isfinite([lower,upper]).all() or np.any(upper<=lower):raise ValueError('invalid XY envelope')
    if not math.isfinite(cell_size_m) or cell_size_m<=0:raise ValueError('invalid cell size')
    shape=np.ceil((upper-lower)/cell_size_m).astype(int)
    if np.prod(shape,dtype=float)>10_000_000:raise ValueError('density grid exceeds cell budget')
    centers=triangles.mean(axis=1)[:,:2]
    if np.any(centers<lower) or np.any(centers>upper):raise ValueError('triangle centroid outside shared envelope')
    bins=np.floor((centers-lower)/cell_size_m).astype(int);bins=np.minimum(bins,shape-1)
    counts=np.bincount(bins[:,1]*shape[0]+bins[:,0],minlength=int(np.prod(shape))).reshape(shape[1],shape[0])
    if counts.sum()!=len(triangles):raise ValueError('triangle density accounting mismatch')
    return counts
