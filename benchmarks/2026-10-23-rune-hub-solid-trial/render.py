"""Matched fixed Rune hub collision views; arms and visuals untouched."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from hub import OUT as ROOT_OUT,ROOT,p,scan
OUT=ROOT_OUT/'open-centers'
ref=p.module('rune_hub_raster_helpers',str(ROOT/'benchmarks/2026-10-23-rune-profile-r3/trial.py'));raster=ref.raster

def data(g,owners,changed,stage):
 colors=np.tile([.58,.60,.63],(len(g),1));colors[np.isin(owners,list(changed))]=[.77,.42,.19]if stage=='candidate'else[.16,.63,.84]
 return(g*.001@np.array([[1,0,0],[0,0,-1],[0,1,0]]),colors,np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),owners,np.zeros((1,1,3),np.uint8))

def main():
 r=json.loads((OUT/'verification.json').read_text());d,c,n=scan.load_nodes(Path(r['source_collision']));_,_,new=scan.load_nodes(Path(r['candidate_collision']));rows=[]
 with tempfile.TemporaryDirectory()as tmp:
  tmp=Path(tmp)
  for bank in ['bank-a','bank-b']:
   context={i for i in n if c[i]==f'rune/banks/{bank}/hub-cluster'};changed=set(r['selected_nodes'])&context
   axis=np.array([.93558540845,-.35310047224,0]);rotation=np.array([[1,0,0],[0,0,-1],[0,1,0]]);normal=axis@rotation
   for scope,ids in [('housings',changed),('hub-context',context)]:
    ids=sorted(ids);source=np.concatenate([n[i]for i in ids]);target=np.concatenate([new[i]for i in ids]);frame=np.concatenate([source,target])*.001@rotation
    for view,direction in [('face',normal),('oblique',normal+np.array([.4,.65,.7])),('reverse',-normal+np.array([0,.25,.1]))]:
     for stage,geos in [('source',n),('candidate',new)]:
      g=np.concatenate([geos[i]for i in ids]);owners=np.concatenate([np.full(len(geos[i]),i)for i in ids]);path=OUT/f'{bank}-{scope}-{view}-{stage}.webp'
      Image.fromarray(raster.raster(data(g,owners,changed,stage),frame,direction,ROOT/'out/rmuc2027-conservative-shape-audit/raster',tmp)).save(path,lossless=True)
      rows.append(dict(bank=bank,scope=scope,view=view,stage=stage,path=str(path),sha256=scan.digest(path)))
   print('Rendered',bank,flush=True)
 (OUT/'renders.json').write_text(json.dumps(dict(views=rows,note='Collision only. Selected fixed hub owners blue before/orange after. Grey context unchanged. Moving arms not shown in isolated hub views.'),indent=2)+'\n')
if __name__=='__main__':main()
