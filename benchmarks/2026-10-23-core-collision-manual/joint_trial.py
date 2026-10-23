"""Explicit outer cylindrical envelope for one hollow joint; comparison only."""
from build import *
from scipy.optimize import minimize

def main():
 d,b=read_glb(source);ni=22;pr=d['meshes'][d['nodes'][ni]['mesh']]['primitives'][0];p=accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000;g=p[accessor(d,b,pr['indices']).reshape(-1,3)];p=np.unique(p,axis=0)
 normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);areas=np.linalg.norm(normal,axis=1);normal/=np.maximum(areas[:,None],1e-20)
 normal*=np.where(normal[np.arange(len(normal)),np.argmax(abs(normal),axis=1)]<0,-1,1)[:,None]
 keys=np.round(normal,4);uni,inv=np.unique(keys,axis=0,return_inverse=True);weight=np.bincount(inv,weights=areas);_,vectors=np.linalg.eigh(np.cov(p.T));axes=[*vectors.T,*uni[np.argsort(weight)[-8:]]]
 trials=[]
 for axis in axes:
  axis=axis/np.linalg.norm(axis);u=np.cross(axis,[0.,0.,1.]);u/=np.linalg.norm(u);v=np.cross(axis,u);q=np.column_stack((p@u,p@v));c=(q.min(0)+q.max(0))/2
  # Smallest enclosing circle for each manually motivated cap/PCA axis.
  opt=minimize(lambda x:x[2],np.r_[c,np.linalg.norm(q-c,axis=1).max()],constraints={'type':'ineq','fun':lambda x:x[2]**2-np.sum((q-x[:2])**2,axis=1)},method='SLSQP',options={'maxiter':200,'ftol':1e-9})
  c2=opt.x[:2];radius=np.linalg.norm(q-c2,axis=1).max();z=p@axis;center=c2[0]*u+c2[1]*v+axis*(z.min()+z.max())/2;length=np.ptp(z)
  trials.append((radius**2*length,center,axis,radius,length))
 _,center,axis,radius,length=min(trials,key=lambda x:x[0]);segments=24;outer=radius/np.cos(np.pi/segments)
 shell=revolve(center,axis,[[-length/2,outer],[length/2,outer]],segments)
 u=np.cross(axis,[0.,0.,1.]);u/=np.linalg.norm(u);v=np.cross(axis,u);theta=np.arange(segments)*2*np.pi/segments;rad=np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v
 caps=[]
 for sign in [-1,1]:
  c=center+axis*length/2*sign;ring=c+outer*rad
  for i in range(segments):
   tri=np.array([c,ring[i],ring[(i+1)%segments]])
   caps.append(tri if sign>0 else tri[::-1])
 new=np.concatenate([shell,np.asarray(caps)]);ad=copy.deepcopy(d);binary=bytearray(b);cp=copy.deepcopy(pr);flat=(new/1000).reshape(-1,3).astype(np.float32);nn=np.cross(new[:,1]-new[:,0],new[:,2]-new[:,0]);nn/=np.linalg.norm(nn,axis=1)[:,None]
 cp['attributes']={'POSITION':append_accessor(ad,binary,flat,'VEC3',5126),'NORMAL':append_accessor(ad,binary,np.repeat(nn,3,axis=0).astype(np.float32),'VEC3',5126)};cp['indices']=append_accessor(ad,binary,np.arange(len(flat),dtype=np.uint32),'SCALAR',5125);cp['extras']={'inspection_only':True,'derived_geometry':True,'source_installed_node':ni,'native_identity_claim':False}
 ad['nodes'][ni]['mesh']=len(ad['meshes']);ad['meshes'].append({'primitives':[cp]});ad['asset'].setdefault('extras',{})['joint_cylinder_trial']={'inspection_only':True,'collision_approved':False}
 target=OUT/'joint-cylinder-comparison.glb';write_glb(target,ad,compact(ad,binary));actual,ab=read_glb(target);assert scene_triangles(actual)==scene_triangles(d)-len(g)+len(new)
 # Distance includes intentionally filled bore surfaces; do not use as an outer silhouette error.
 dev=measure(g,new)
 result={'node':ni,'source':str(source),'candidate':str(target),'source_sha256':digest(source),'candidate_sha256':digest(target),'before':len(g),'after':len(new),'placed_saving':2*(len(g)-len(new)),'prototype_parameters':{'coordinate_frame':'mesh-local installed GLB axes; not runtime FLU','center_m':(center/1000).tolist(),'axis_unit_vector':axis.tolist(),'radius_m':float(radius/1000),'length_m':float(length/1000),'mesh_radial_segments':segments,'mesh_radius_m':float(outer/1000),'solid':True},'source_to_envelope_surface_distance_mm':dev,'limitations':'Comparison-only solid cylinder. Intentionally fills all housing openings and internal void. Enclosing cylinder can enlarge outer silhouette and block existing clearances. Not integrated into the local profile candidate or approved for contacts. Parameter JSON is an experimental description, not a supported runtime schema.'}
 (OUT/'joint-cylinder.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
