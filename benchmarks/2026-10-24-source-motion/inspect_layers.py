from pathlib import Path
import numpy as np,json
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/rmuc2027-source-motion'
z=np.load(ROOT/'out/rmuc2027-equipment-pipeline/outpost/fixed/upper-cluster/native.npz');mask=z['unit_ids']==1;ii=np.flatnonzero(mask);tri=z['triangles'][mask];p=z['positions_mm']
_,inv=np.unique(np.round(p,5),axis=0,return_inverse=True);tt=inv[tri];edges=np.concatenate([tt[:,[0,1]],tt[:,[1,2]],tt[:,[2,0]]]);n,labels=connected_components(coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(inv.max()+1,inv.max()+1)),directed=False)
lab=labels[tt[:,0]];rows=[]
for k in np.unique(lab):
 idx=ii[lab==k];pts=p[np.unique(z['triangles'][idx])];r={'island':int(k),'triangles':len(idx),'bounds_mm':[pts.min(0).tolist(),pts.max(0).tolist()]};rows.append(r)
rows.sort(key=lambda r:-r['triangles']);(OUT/'outpost-upper-islands.json').write_text(json.dumps(rows,indent=2)+'\n');np.savez_compressed(OUT/'outpost-upper-island-ids.npz',triangle_indices=ii,island_ids=lab)
for r in rows:
 if r['triangles']>=100: print(r['island'],r['triangles'],np.round(r['bounds_mm'],1).tolist())
print('ISLANDS',len(rows))
b=json.load(open(OUT/'analytic-inventory.json'))
print('BASE CENTRAL UPPER UNITS')
for c in b['components']:
 if c['id']!='base/source-model':continue
 for u in c['units']:
  bb=u['bounds_mm']
  if bb and bb[0][0]>=-125 and bb[1][0]<=125 and bb[1][1]>990 and bb[0][1]>900:print(u['source_id'],u['kind'],np.round(bb,1).tolist())
