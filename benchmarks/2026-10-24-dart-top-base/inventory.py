"""Inspect retained Dart crossbars/deck in the accepted slimmer-beam reference."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
ROOT=Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT/'benchmarks/2026-10-24-dart-beams-refined'))
import importlib.util
spec=importlib.util.spec_from_file_location('accepted_dart_sides',ROOT/'benchmarks/2026-10-24-dart-beams-refined/export.py');ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
hub=ref.hub;local_geometry=ref.local_geometry
from gltf_scene import read_glb
OUT=ROOT/'out/rmuc2027-dart-top-base';STAGE=ROOT/'out/rmuc2027-dart-beams-refined/paired-stage.json'
def islands(g):
 v,inv=np.unique(np.round(g.reshape(-1,3),2),axis=0,return_inverse=True);f=inv.reshape(-1,3);e=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);_,labels=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(v),len(v))),directed=False)
 return [np.flatnonzero(labels[f[:,0]]==label)for label in np.unique(labels)]
def main():
 stage=json.loads(STAGE.read_text());path=Path(stage['collision_assets']['arena-static']['path']);d,b=read_glb(path);rows=[]
 for node in [354,587]:
  groups=local_geometry(d,b,node);g=np.concatenate(groups[:-1]);items=[]
  for ids in islands(g):
   if not len(ids):continue
   p=g[ids].reshape(-1,3);items.append(dict(triangles=len(ids),triangle_indices=ids.tolist(),bounds_mm=[p.min(0).tolist(),p.max(0).tolist()]))
  rows.append(dict(node=node,source_triangles=len(g),islands=sorted(items,key=lambda x:-x['triangles'])))
  print('NODE',node,len(g))
  for i,x in enumerate(rows[-1]['islands'][:35]):print(i,x['triangles'],np.round(x['bounds_mm'],1).tolist())
 (OUT/'inventory.json').write_text(json.dumps(dict(source=str(path),source_sha256=hub.scan.digest(path),records=rows),indent=2)+'\n')
if __name__=='__main__':main()
