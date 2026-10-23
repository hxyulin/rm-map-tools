"""Matched local hardware and Rune profile collision comparisons."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from inventory import ROOT,OUT,hub
ref=hub.p.module('next_collision_trial_raster',str(ROOT/'benchmarks/2026-10-23-rune-profile-r3/trial.py'));raster=ref.raster

def dataset(nodes,ids,records,stage,basis):
 geos=[];colors=[]
 for node in sorted(ids):
  g=nodes[node];color=np.tile([.58,.60,.63],(len(g),1))
  if node in records:
   row=records[node]
   if stage=='source':
    mask=np.concatenate([np.isin(np.arange(s['source_triangles']),s['selected_triangle_indices'])for s in row['selectors']]);color[mask]=[.16,.63,.84]
   else:color[row['retained_triangles']:]=[.77,.42,.19]
  geos.append(g);colors.append(color)
 g=np.concatenate(geos)*.001@basis
 return(g,np.concatenate(colors),np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),np.zeros(len(g),np.int32),np.zeros((1,1,3),np.uint8))
def main():
 rows=[]
 with tempfile.TemporaryDirectory()as tmp:
  for asset in ['outpost','rune']:
   r=json.loads((OUT/f'{asset}-verification.json').read_text());d,c,old=hub.scan.load_nodes(Path(r['source_collision']));_,_,new=hub.scan.load_nodes(Path(r['candidate_collision']));records={x['node']:x for x in r['records']};basis=np.eye(3)
   scopes=[('whole',set(old))]
   if asset=='outpost':scopes+=[('lower',{14,23}),('upper',{25})];directions=[('front',np.array([1,.5,.7])@basis),('oblique',np.array([-1,.5,1])@basis)]
   else:
    scopes+=[('arm-0',{i for i in old if c[i]and c[i].startswith('rune/banks/bank-a/arm-0')}),('strip',{154})]
   for scope,ids in scopes:
    if asset=='rune':
     pt=old[154 if scope=='strip'else 152].reshape(-1,3);_,_,axes=np.linalg.svd(pt-pt.mean(0),full_matrices=False);directions=[('front',axes[2]),('oblique',axes[2]+.5*axes[1])]
    datasets={stage:dataset(nodes,ids,records,stage,basis)for stage,nodes in [('source',old),('candidate',new)]};frame=np.concatenate([x[0]for x in datasets.values()])
    for camera,direction in directions:
     for stage,ds in datasets.items():
      path=OUT/f'{asset}-{scope}-{camera}-{stage}.webp';Image.fromarray(raster.raster(ds,frame,direction,ROOT/'out/rmuc2027-conservative-shape-audit/raster',Path(tmp))).save(path,lossless=True);rows.append(dict(asset=asset,scope=scope,camera=camera,stage=stage,path=str(path),sha256=hub.scan.digest(path)))
 (OUT/'renders.json').write_text(json.dumps(rows,indent=2)+'\n');print('Rendered',len(rows),'matched images.')
if __name__=='__main__':main()
