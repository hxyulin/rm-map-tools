"""Rank current Outpost and rotating Rune owners without merging motion groups."""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-rune-hub-solid-trial'));import hub
from gltf_scene import scene_nodes
OUT=ROOT/'out/rmuc2027-outpost-rune-next';STAGE=ROOT/'out/rmuc2027-dart-top-base/paired-stage.json';BINDINGS=ROOT.parent/'rm-simulator/field-2027/rmuc2027-bindings.json'
def main():
 stage=json.loads(STAGE.read_text());bindings=json.loads(BINDINGS.read_text());motion={name:[k for k,row in enumerate(bindings['rune_motion'])if name in row['bodies']]for row in bindings['rune_motion']for name in row['bodies']};report={}
 for asset in ['outpost','rune']:
  path=Path(stage['collision_assets'][asset]['path']);assert hub.scan.digest(path)==stage['collision_assets'][asset]['sha256'];d,c,n=hub.scan.load_nodes(path);rows=[]
  for node,g in n.items():
   points=np.unique(g.reshape(-1,3),axis=0);center=points.mean(0);_,_,axes=np.linalg.svd(points-center,full_matrices=False);extents=np.ptp((points-center)@axes.T,axis=0)
   rows.append(dict(node=node,name=d['nodes'][node]['name'],component=c[node],triangles=len(g),pca_extents_mm=extents.tolist(),bounds_mm=[points.min(0).tolist(),points.max(0).tolist()],rune_motion_groups=motion.get(d['nodes'][node]['name'],[])))
  rows.sort(key=lambda x:-x['triangles']);report[asset]=dict(source=str(path),source_sha256=hub.scan.digest(path),triangles=sum(len(g)for g in n.values()),owners=rows)
  print(asset,report[asset]['triangles'],'triangles')
  for row in rows[:25]:print(row['node'],row['triangles'],np.round(row['pca_extents_mm'],1).tolist(),'MOTION',row['rune_motion_groups'],row['component'])
 report['input_pins']={str(p):hub.scan.digest(p)for p in [STAGE,BINDINGS]};(OUT/'inventory.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
