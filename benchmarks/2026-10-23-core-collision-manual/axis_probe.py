from profile_probe import *
d,b=read_glb(source)
for ni in [17,26,1284]:
 pr=d['meshes'][d['nodes'][ni]['mesh']]['primitives'][0];p=accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000;t=accessor(d,b,pr['indices']).reshape(-1,3);g=p[t];mean=p.mean(0);_,v=np.linalg.eigh(np.cov(p.T));a=v[:,-1];z=(g-mean)@a
 long=z.ptp(1) if hasattr(z,'ptp') else np.ptp(z,axis=1)
 n=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-20)
 ids=long>.7*long.max();_,v=np.linalg.eigh(n[ids].T@n[ids]);a=v[:,0];u=np.cross(a,[0,0,1]);u/=np.linalg.norm(u);v=np.cross(a,u);basis=np.column_stack((u,v,a));q=np.unique(g[ids].reshape(-1,3),axis=0)@basis
 # paired inner and outer circle: jointly fit concentric radii via robust least squares.
 def fun(x):
  rr=np.linalg.norm(q[:,:2]-x[:2],axis=1);return np.minimum(abs(rr-x[2]),abs(rr-x[3]))
 c=(q[:,:2].min(0)+q[:,:2].max(0))/2;rr=np.linalg.norm(q[:,:2]-c,axis=1)
 o=least_squares(fun,np.r_[c,np.quantile(rr,.15),np.quantile(rr,.85)],max_nfev=500,loss='soft_l1',f_scale=.01)
 center=basis@np.r_[o.x[:2],np.mean(p@a)];qq=p-center;zz=qq@a;rr=np.linalg.norm(qq-np.outer(zz,a),axis=1)
 print('\n',ni,'axis',a,'radii',o.x[2:],'res',np.max(fun(o.x)),'zrange',zz.min(),zz.max())
 bins=np.round(zz,2)
 from collections import Counter
 for k,nc in Counter(bins).most_common(16):print(k,nc,np.round(np.percentile(rr[bins==k],[0,10,50,90,100]),3))
 np.savez(OUT/f'axis-{ni}.npz',center=center,axis=a,p=p,z=zz,r=rr)
