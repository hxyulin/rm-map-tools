# SPDX-License-Identifier: MIT OR Apache-2.0
"""Study boundary relaxation in four current mesh sections; no package is modified.

Distances are relative to the already simplified current mesh, not original STEP.
Grid welding can merge components and is not a production collision contract.
"""
import json
from pathlib import Path
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from gltf_scene import read_glb, accessor, write_glb
from simplify_package import simplify_mesh, append_accessor
from mesh_quality import deviation
import meshoptimizer as mo
import math
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
def simplify_mesh(points, triangles, error_m):
    """Experimental boundary relaxation. Do not use as a production collider."""
    points, triangles = np.asarray(points, dtype=np.float32), np.asarray(triangles)
    if points.ndim != 2 or points.shape[1] != 3 or triangles.ndim != 2 or triangles.shape[1] != 3 or not np.issubdtype(triangles.dtype, np.integer):
        raise ValueError('expected Nx3 positions and integer Mx3 triangles')
    if not math.isfinite(error_m) or error_m <= 0:
        raise ValueError('expected finite positive mesh error')
    if not np.isfinite(points).all() or not len(triangles) or triangles.min() < 0 or triangles.max() >= len(points):
        raise ValueError('invalid triangle mesh')
    points, inverse = np.unique(np.asarray(points, dtype=np.float32), axis=0, return_inverse=True)
    indices = np.ascontiguousarray(inverse[triangles.ravel()], dtype=np.uint32)
    points = np.ascontiguousarray(points)
    result = np.empty_like(indices)
    error = np.zeros(1, np.float32)
    count = mo.simplify(result, indices, points, target_index_count=3,
                        target_error=error_m, options=mo.SIMPLIFY_ERROR_ABSOLUTE,
                        result_error=error)
    if count % 3 or count > len(indices) or not np.isfinite(error[0]) or error[0] > error_m + 1e-7:
        raise ValueError(f'invalid simplifier result: count={count}, input={len(indices)}, error={error[0]}, limit={error_m}')
    triangles = result[:count].reshape(-1, 3)
    # Never let a closed or degenerate disconnected detail disappear entirely.
    source = indices.reshape(-1, 3)
    rows = np.repeat(source[:, 0], 2)
    cols = source[:, 1:].ravel()
    graph = coo_matrix((np.ones(len(rows), dtype=np.uint8), (rows, cols)), shape=(len(points), len(points))).tocsr()
    _, labels = connected_components(graph, directed=False)
    missing = ~np.isin(labels[source[:, 0]], labels[triangles.ravel()])
    if missing.any():
        triangles = np.vstack([triangles, source[missing]])
    used, inverse = np.unique(triangles, return_inverse=True)
    return points[used], inverse.reshape(-1, 3), float(error[0])


root=Path(__file__).resolve().parents[2]
package=root.parent/'rm-simulator/local-assets/field'
out=root/'out/border-probe'
out.mkdir(exist_ok=True)
results=[]
for asset,scope,node,pi in [('resource-zone','',1,1),('dart-station','',1,5),('base','equipment',1,1),('dart-station','',2,0)]:
    d,b=read_glb(package/scope/(asset+'.glb'))
    pr=d['meshes'][d['nodes'][node]['mesh']]['primitives'][pi]
    v=accessor(d,b,pr['attributes']['POSITION']).copy()
    t=accessor(d,b,pr['indices']).reshape(-1,3).copy()
    def save(v,t,name):
        doc={'asset':{'version':'2.0','extras':{'study_only':True}},'scene':0,'scenes':[{'nodes':[0]}],
             'nodes':[{'mesh':0}], 'meshes':[{'primitives':[]}], 'materials':[d['materials'][pr['material']]],'accessors':[],'bufferViews':[]}
        binary=bytearray()
        position=append_accessor(doc,binary,np.asarray(v,dtype='<f4'),'VEC3',5126)
        indices=append_accessor(doc,binary,np.asarray(t,dtype='<u4').reshape(-1),'SCALAR',5125)
        doc['meshes'][0]['primitives']=[{'attributes':{'POSITION':position},'indices':indices,'material':0}]
        doc['buffers']=[{'byteLength':len(binary)}]
        write_glb(out/name,doc,bytes(binary))
    prefix=f'{asset}-n{node}-p{pi}'
    save(v,t,prefix+'-before.glb')
    for error_mm in (.25, .5, 1, 2):
        grid_mm = 0
        start=time.perf_counter()
        source = v if grid_mm==0 else np.round(v.astype(float)/(grid_mm/1000))*(grid_mm/1000)
        w,u,e=simplify_mesh(source,t,error_mm/1000)
        q=deviation(v,t,w,u,count=4096)
        row=dict(asset=asset,node=node,primitive=pi,grid_mm=grid_mm,error_mm=error_mm,
                 before=len(t),after=len(u),sampled_max_mm=q['max']*1000,
                 sampled_p99_mm=q['p99']*1000,samples=q['sample_count'],seconds=time.perf_counter()-start)
        results.append(row);print(row,flush=True)
        save(w,u,prefix+f'-error-{error_mm}.glb')
        Path(__file__).with_name('border-probe.json').write_text(json.dumps(results,indent=2)+'\n')
