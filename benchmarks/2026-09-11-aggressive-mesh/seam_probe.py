# SPDX-License-Identifier: MIT OR Apache-2.0
"""Study grid welding in four current mesh sections; no package is modified.

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
root=Path(__file__).resolve().parents[2]
package=root.parent/'rm-simulator/local-assets/field'
out=root/'out/seam-probe'
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
    for grid_mm in (0,.001,.01,.1):
        start=time.perf_counter()
        source = v if grid_mm==0 else np.round(v.astype(float)/(grid_mm/1000))*(grid_mm/1000)
        w,u,e=simplify_mesh(source,t,.002)
        q=deviation(v,t,w,u,count=1024)
        row=dict(asset=asset,node=node,primitive=pi,grid_mm=grid_mm,error_mm=2,
                 before=len(t),after=len(u),sampled_max_mm=q['max']*1000,
                 sampled_p99_mm=q['p99']*1000,samples=q['sample_count'],seconds=time.perf_counter()-start)
        results.append(row);print(row,flush=True)
        save(w,u,prefix+f'-grid-{grid_mm}.glb')
        Path(__file__).with_name('seam-probe.json').write_text(json.dumps(results,indent=2)+'\n')
