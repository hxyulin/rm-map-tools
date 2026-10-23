import trial
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

def components(g):
 p,inv=np.unique(np.round(g.reshape(-1,3)/.02).astype(np.int64),axis=0,return_inverse=True);t=inv.reshape(-1,3);e=np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]);_,labels=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(p),len(p))).tocsr(),directed=False)
 return labels[t[:,0]]
if __name__=='__main__':
 d,b=trial.read_glb(trial.PKG/'arena-static.glb')
 for i in [19,208,220]:
  for j,p in enumerate(d['meshes'][d['nodes'][i]['mesh']]['primitives']):
   g=trial.load(d,b,p);c=components(g);print(i,j,len(g),len(np.unique(c)))
   for k in sorted(np.unique(c),key=lambda k:-(c==k).sum())[:15]:
    q=g[c==k]; print(' ',k,len(q),np.round(np.ptp(q.reshape(-1,3),axis=0),1))
