# SPDX-License-Identifier: MIT OR Apache-2.0
"""Count exact-welded open edges in the largest current mesh sections."""
import json
from pathlib import Path
import sys
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from gltf_scene import read_glb, accessor
root=Path(__file__).resolve().parents[2].parent/'rm-simulator/local-assets/field'
results=[]
for name,scope,node,pi in [('resource-zone','',1,1),('dart-station','',1,5),('base','equipment',1,1),('dart-station','',2,0)]:
    d,b=read_glb(root/scope/(name+'.glb'))
    p=d['meshes'][d['nodes'][node]['mesh']]['primitives'][pi]
    v=accessor(d,b,p['attributes']['POSITION'])
    t=accessor(d,b,p['indices']).reshape(-1,3)
    v,inv=np.unique(v,axis=0,return_inverse=True)
    t=inv[t]
    edges=np.sort(np.vstack([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1)
    e,c=np.unique(edges,axis=0,return_counts=True)
    boundary=np.unique(e[c==1])
    graph=coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(v),len(v))).tocsr()
    n,labels=connected_components(graph,directed=False)
    counts=np.bincount(labels[t[:,0]])
    r=dict(asset=name,node=node,primitive=pi,triangles=len(t),welded_vertices=len(v),
           boundary_vertices=len(boundary),open_edges=int((c==1).sum()),components=n,
           triangles_in_components_le_12=int(counts[counts<=12].sum()),
           triangles_touching_boundary=int(np.isin(t,boundary).any(axis=1).sum()))
    results.append(r);print(r,flush=True)
Path(__file__).with_name('boundaries.json').write_text(json.dumps(results,indent=2)+'\n')
