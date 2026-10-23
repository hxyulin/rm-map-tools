from inspect_parts import *
from gltf_scene import read_glb,accessor
from scipy.optimize import least_squares

def fit(points):
 c=points.mean(0);_,v=np.linalg.eigh(np.cov(points.T));axis=v[:,-1];z=(points-c)@axis
 mid=points[(z>np.quantile(z,.3))&(z<np.quantile(z,.7))]
 def fun(x):
  a=x[3:6]/np.linalg.norm(x[3:6]);q=mid-x[:3];return np.linalg.norm(q-np.outer(q@a,a),axis=1)-x[6]
 q=mid-c;rad=np.median(np.linalg.norm(q-np.outer(q@axis,axis),axis=1));opt=least_squares(fun,np.r_[c,axis,rad],max_nfev=200)
 axis=opt.x[3:6]/np.linalg.norm(opt.x[3:6]);center=opt.x[:3];center+=axis*((points.mean(0)-center)@axis)
 q=points-center;z=q@axis;rho=np.linalg.norm(q-np.outer(z,axis),axis=1)
 return center,axis,z,rho
if __name__=='__main__':
 d,b=read_glb(source)
 for ni in [17,26,1284]:
  pr=d['meshes'][d['nodes'][ni]['mesh']]['primitives'][0];p=np.unique(accessor(d,b,pr['attributes']['POSITION']),axis=0).astype(float)*1000
  c,a,z,r=fit(p);print('\nNODE',ni,'center',c,'axis',a,'levels:')
  bins=np.round(z,2)
  from collections import Counter
  for k,n in Counter(bins).most_common(25):
   rr=r[bins==k];print(k,n, np.round(np.percentile(rr,[0,10,50,90,100]),3))
  np.savez(OUT/f'profile-{ni}.npz',p=p,center=c,axis=a,z=z,r=r)
