"""Two explicit manual collision profiles, starting from exact installed geometry."""
from inspect_parts import *
import copy,hashlib
from gltf_scene import read_glb,accessor,write_glb,scene_nodes
from simplify_package import append_accessor,compact,scene_triangles
from mesh_quality import distances

def samples(g):return np.concatenate([g.reshape(-1,3),g.mean(1),(g[:,0]+g[:,1])/2,(g[:,1]+g[:,2])/2,(g[:,2]+g[:,0])/2])
def measure(a,b):
 vals=[distances(samples(x),y.reshape(-1,3),np.arange(y.size//3).reshape(-1,3)) for x,y in [(a,b),(b,a)]]
 return {'forward_max_mm':float(vals[0].max()),'reverse_max_mm':float(vals[1].max()),'samples':sum(map(len,vals))}
def revolve(center,axis,profile,segments):
 axis=np.asarray(axis);axis/=np.linalg.norm(axis);u=np.cross(axis,[0.,0.,1.]);u/=np.linalg.norm(u);v=np.cross(axis,u)
 theta=np.arange(segments)*2*np.pi/segments;radial=np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v
 p=np.concatenate([center+z*axis+radius*radial for z,radius in profile]);t=[]
 for j in range(len(profile)-1):
  for i in range(segments):
   a=j*segments+i;b=j*segments+(i+1)%segments;c=(j+1)*segments+i;d=(j+1)*segments+(i+1)%segments;t.extend([[a,b,c],[b,d,c]])
 return p[np.asarray(t)]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 d,b=read_glb(source);ad=copy.deepcopy(d);binary=bytearray(b);records=[]
 x=np.load(OUT/'axis-17.npz');profile=[[-381.23149,57.7],[-380.93144,58],[-370.2314,58],[65.92,58.143],[70.57,59.278],[74.81,61.484],[78.41,64.633],[81.16,68.546],[82.90,73],[84.51,75.3],[86.97,76],[100.47,76],[100.7686,75.7],[100.7686,72.5]]
 for ni in [17,1284]:
  mesh=d['meshes'][d['nodes'][ni]['mesh']];assert len(mesh['primitives'])==1;pr=mesh['primitives'][0];p=accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000;g=p[accessor(d,b,pr['indices']).reshape(-1,3)]
  if ni==17:
   c=x['center'];axis=x['axis'];prof=profile;seg=32;description='Measured flanged tube meridian; retains flare, upper annular lip and open ends. Omits tiny circumferential grooves/chamfers.'
  else:
   c=(p.min(0)+p.max(0))/2;axis=np.array([0.,1.,0.]);z=(p-c)@axis;prof=[[float(z.min()),10],[float(z.max()),10]];seg=24;description='Straight open sleeve of 10 mm radius; removes fine thread corrugation. Both axial ends remain open.'
  new=revolve(c,axis,prof,seg);dev=measure(g,new);print(ni,len(g),len(new),dev,flush=True)
  assert max(dev['forward_max_mm'],dev['reverse_max_mm'])<1.0
  # Preserve source orientation: compare aggregate normal/radial alignment.
  for triangles in [g,new]:
   normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);q=triangles.mean(1)-c;q-=np.outer(q@axis,axis)
   if triangles is g:source_sign=np.sum(normals*q)
   elif source_sign*np.sum(normals*q)<0:new=new[:,::-1]
  cp=copy.deepcopy(pr);flat=(new/1000).reshape(-1,3).astype(np.float32);normal=np.cross(new[:,1]-new[:,0],new[:,2]-new[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
  cp['attributes']={'POSITION':append_accessor(ad,binary,flat,'VEC3',5126),'NORMAL':append_accessor(ad,binary,np.repeat(normal,3,axis=0).astype(np.float32),'VEC3',5126)};cp['indices']=append_accessor(ad,binary,np.arange(len(flat),dtype=np.uint32),'SCALAR',5125)
  cp['extras']={**cp.get('extras',{}),'inspection_only':True,'derived_geometry':True,'source_installed_node':ni,'native_identity_claim':False}
  ad['nodes'][ni]['mesh']=len(ad['meshes']);ad['meshes'].append({**copy.deepcopy(mesh),'primitives':[cp]})
  records.append(dict(node=ni,before=len(g),after=len(new),description=description,segments=seg,axis=axis.tolist(),center_mm=c.tolist(),profile_z_radius_mm=prof,sampled_deviation=dev,source_bounds_mm=[g.min((0,1)).tolist(),g.max((0,1)).tolist()],candidate_bounds_mm=[new.min((0,1)).tolist(),new.max((0,1)).tolist()]))
 ad['asset'].setdefault('extras',{})['core_collision_manual_trial']={'inspection_only':True,'collision_approved':False,'source_sha256':digest(source)}
 target=OUT/'tech-core-collision.glb';write_glb(target,ad,compact(ad,binary));actual,ab=read_glb(target)
 checks=[]
 for ni,(old,newnode) in enumerate(zip(d['nodes'],actual['nodes'])):
  assert {k:v for k,v in old.items()if k!='mesh'}=={k:v for k,v in newnode.items()if k!='mesh'}
  if 'mesh'not in old or ni in [17,1284]:continue
  pp=d['meshes'][old['mesh']]['primitives'];qq=actual['meshes'][newnode['mesh']]['primitives'];assert len(pp)==len(qq)
  for a,bb in zip(pp,qq):
   assert {k:v for k,v in a.items()if k not in ['attributes','indices']}=={k:v for k,v in bb.items()if k not in ['attributes','indices']}
   for key in a['attributes']:assert np.array_equal(accessor(d,b,a['attributes'][key]),accessor(actual,ab,bb['attributes'][key]))
   assert np.array_equal(accessor(d,b,a['indices']),accessor(actual,ab,bb['indices']))
  checks.append(ni)
 assert d['materials']==actual['materials'];assert d['scenes']==actual['scenes']
 for row in records:
  ni=row['node'];pr=actual['meshes'][actual['nodes'][ni]['mesh']]['primitives'][0];pts=accessor(actual,ab,pr['attributes']['POSITION']).astype(float)*1000;g=pts[accessor(actual,ab,pr['indices']).reshape(-1,3)];assert np.isfinite(g).all();assert np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-9
  row['reopened_triangles']=len(g)
 for p,h in ref['pins'].items():assert digest(Path(p))==h
 result={'source':str(source),'source_sha256':digest(source),'candidate':str(target),'candidate_sha256':digest(target),'before_per_unit':scene_triangles(d),'after_per_unit':scene_triangles(actual),'placed_saving':2*(scene_triangles(d)-scene_triangles(actual)),'records':records,'unchanged_mesh_nodes':len(checks),'node_names_extras_transforms_ancestry_exact':True,'materials_exact':True,'installed_inputs_unchanged':True,'visual_unchanged':True,'limitations':'Finite surface samples against installed input, not continuous/native/contact or runtime approval. Open shell profiles deliberately retain openings; no watertight solid claim. Detailed joint housings and crucial slotted face remain unchanged.'}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
