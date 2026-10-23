"""Source collision context for selecting Outpost and Rune approximations."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from inventory import ROOT,OUT,hub
ref=hub.p.module('next_collision_raster',str(ROOT/'benchmarks/2026-10-23-rune-profile-r3/trial.py'));raster=ref.raster

def dataset(nodes,ids,selected):
 g=np.concatenate([nodes[i]for i in ids])*.001;colors=np.concatenate([np.tile([.16,.63,.84]if i in selected else[.58,.60,.63],(len(nodes[i]),1))for i in ids]);return(g,colors,np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),np.zeros(len(g),np.int32),np.zeros((1,1,3),np.uint8))
def main():
 r=json.loads((OUT/'inventory.json').read_text());rows=[]
 with tempfile.TemporaryDirectory()as tmp:
  for asset in ['outpost','rune']:
   d,c,n=hub.scan.load_nodes(Path(r[asset]['source']));scopes=[('whole',set(n),{25,14}if asset=='outpost'else{i for i in n if c[i]and c[i].startswith('rune/banks/bank-a/arm-0')})]
   if asset=='outpost':scopes += [('upper',{25},{25}),('lower',{14},{14})]
   else:scopes += [('arm-0',{i for i in n if c[i]and c[i].startswith('rune/banks/bank-a/arm-0')},set(n)),('thin-plate',{154},{154})]
   for label,ids,sel in scopes:
    ds=dataset(n,sorted(ids),sel)
    for camera,direction in [('front',[1,-.38,.12]),('oblique',[1,-1,.5])]:
     path=OUT/f'{asset}-{label}-{camera}.webp';Image.fromarray(raster.raster(ds,ds[0],np.array(direction),ROOT/'out/rmuc2027-conservative-shape-audit/raster',Path(tmp))).save(path,lossless=True);rows.append(dict(asset=asset,scope=label,camera=camera,path=str(path),sha256=hub.scan.digest(path)))
 (OUT/'reference-renders.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':main()
