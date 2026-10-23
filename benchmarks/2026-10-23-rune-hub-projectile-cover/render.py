"""Matched source/trimmed/enclosing hub collision views."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from cover import OUT,ROOT,PREVIOUS,p,scan
ref=p.module('hub_cover_raster_helpers',str(ROOT/'benchmarks/2026-10-23-rune-profile-r3/trial.py'));raster=ref.raster

def data(nodes,ids,hubids,stage):
 ids=sorted(i for i in ids if i in nodes);g=np.concatenate([nodes[i]for i in ids]);owners=np.concatenate([np.full(len(nodes[i]),i)for i in ids]);colors=np.tile([.58,.60,.63],(len(g),1));colors[np.isin(owners,list(hubids))]=[.77,.42,.19]if stage=='candidate'else[.16,.63,.84]
 return(g*.001@np.array([[1,0,0],[0,0,-1],[0,1,0]]),colors,np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),owners,np.zeros((1,1,3),np.uint8))

def main():
 r=json.loads((OUT/'verification.json').read_text());old=json.loads(PREVIOUS.read_text());d,c,source=scan.load_nodes(Path(r['source_collision']));_,_,previous=scan.load_nodes(Path(old['candidate_collision']));_,_,candidate=scan.load_nodes(Path(r['candidate_collision']));rows=[]
 with tempfile.TemporaryDirectory()as tmp:
  tmp=Path(tmp)
  for bank in ['bank-a','bank-b']:
   normal=np.array([.93558540845,-.35310047224,0])@np.array([[1,0,0],[0,0,-1],[0,1,0]]);hubids={i for i in source if c[i]==f'rune/banks/{bank}/hub-cluster'}
   for scope in ['hub','bank']:
    ids=hubids|({i for i in source if c[i].startswith(f'rune/banks/{bank}/arm-')}if scope=='bank'else set());datasets={stage:data(nodes,ids,hubids,stage)for stage,nodes in [('source',source),('previous',previous),('candidate',candidate)]};frame=np.concatenate([x[0]for x in datasets.values()])
    for view,direction in [('oblique',normal+np.array([.4,.65,.7])),('face',normal),('reverse',-normal+np.array([0,.25,.1]))]:
     for stage,a in datasets.items():
      path=OUT/f'{bank}-{scope}-{view}-{stage}.webp';Image.fromarray(raster.raster(a,frame,direction,ROOT/'out/rmuc2027-conservative-shape-audit/raster',tmp)).save(path,lossless=True);rows.append(dict(bank=bank,scope=scope,view=view,stage=stage,path=str(path),sha256=scan.digest(path)))
   print('Rendered',bank,flush=True)
 (OUT/'renders.json').write_text(json.dumps(dict(views=rows,note='Detailed source, prior trimmed hulls, and enclosing hulls share cameras/frame. Actual visuals unchanged.'),indent=2)+'\n')
if __name__=='__main__':main()
