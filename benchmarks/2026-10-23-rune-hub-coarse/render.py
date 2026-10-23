"""Matched prior/coarse Rune hub views, with optional unchanged arm context."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from coarse import OUT,ROOT,BASE,p,scan
ref=p.module('coarse_rune_raster_helpers',str(ROOT/'benchmarks/2026-10-23-rune-profile-r3/trial.py'));raster=ref.raster

def data(nodes,ids,selected,stage):
 ids=sorted(i for i in ids if i in nodes);g=np.concatenate([nodes[i]for i in ids]);owners=np.concatenate([np.full(len(nodes[i]),i)for i in ids]);color=np.tile([.58,.60,.63],(len(g),1));color[np.isin(owners,list(selected))]=[.77,.42,.19]if stage=='candidate'else[.16,.63,.84]
 return(g*.001@np.array([[1,0,0],[0,0,-1],[0,1,0]]),color,np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),owners,np.zeros((1,1,3),np.uint8))

def main():
 old=json.loads(BASE.read_text());d,c,before=scan.load_nodes(Path(old['candidate_collision']));rows=[]
 with tempfile.TemporaryDirectory()as tmp:
  tmp=Path(tmp)
  for variant in ['simple-frame','coarse-hub']:
   out=OUT/variant;r=json.loads((out/'verification.json').read_text());_,_,after=scan.load_nodes(Path(r['candidate_collision']));selected=set(r['selected_nodes'])
   for bank in ['bank-a','bank-b']:
    normal=np.array([.93558540845,-.35310047224,0])@np.array([[1,0,0],[0,0,-1],[0,1,0]])
    for scope in ['hub','bank']:
     ids={i for i in before if c[i]==f'rune/banks/{bank}/hub-cluster' or(scope=='bank'and c[i].startswith(f'rune/banks/{bank}/arm-'))}
     datasets={stage:data(nodes,ids,selected,stage)for stage,nodes in [('previous',before),('candidate',after)]};frame=np.concatenate([a[0]for a in datasets.values()])
     for view,direction in [('oblique',normal+np.array([.4,.65,.7])),('face',normal),('reverse',-normal+np.array([0,.25,.1]))]:
      for stage,a in datasets.items():
       path=out/f'{bank}-{scope}-{view}-{stage}.webp';Image.fromarray(raster.raster(a,frame,direction,ROOT/'out/rmuc2027-conservative-shape-audit/raster',tmp)).save(path,lossless=True);rows.append(dict(variant=variant,bank=bank,scope=scope,view=view,stage=stage,path=str(path),sha256=scan.digest(path)))
   print('Rendered',variant,flush=True)
 (OUT/'renders.json').write_text(json.dumps(dict(views=rows,note='Compared to approved open-centers proposal. Blue old changed fixed owners, orange new native previews, grey unchanged context. Visual assets unchanged.'),indent=2)+'\n')
if __name__=='__main__':main()
