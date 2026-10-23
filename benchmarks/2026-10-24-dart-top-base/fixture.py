"""Create real-trimesh CCD fixtures for selected Dart frame profiles."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from export import OUT,ROOT,hub,local_geometry
from gltf_scene import read_glb,accessor,scene_nodes

def entry(origin,direction,eq):
 a=eq[:,:3]@direction;b=eq[:,:3]@origin+eq[:,3];parallel=abs(a)<1e-12
 if (b[parallel]>0).any():return None
 lo=max(0.,float(np.max(-b[a<0]/a[a<0],initial=0)));hi=min(2500.,float(np.min(-b[a>0]/a[a>0],initial=2500)))
 return lo if lo<=hi else None

def ray_mesh(origin,direction,triangles):
 e1=triangles[:,1]-triangles[:,0];e2=triangles[:,2]-triangles[:,0];h=np.cross(np.broadcast_to(direction,e2.shape),e2);det=np.einsum('ij,ij->i',e1,h);valid=abs(det)>1e-10;inv=np.zeros(len(det));inv[valid]=1/det[valid];delta=origin-triangles[:,0];u=inv*np.einsum('ij,ij->i',delta,h);q=np.cross(delta,e1);v=inv*(q@direction);t=inv*np.einsum('ij,ij->i',e2,q);valid&=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(t>=0)
 return float(t[valid].min())if valid.any()else None

def main():
 manifest_path=ROOT.parent/'rm-simulator/field-2027/manifest.json';manifest=json.loads(manifest_path.read_text());translation=np.array([0.,0.,-manifest['floor_top_source_z_m']])
 r=json.loads((OUT/'verification.json').read_text());d,b=read_glb(Path(r['source_collision']));a,ab=read_glb(Path(r['candidate_collision']));world={i:w for i,w,parent in scene_nodes(d)};meshes=[];cases=[]
 for row in r['records']:
  node=row['node'];matrix=world[node];rotation=matrix[:3,:3];primitive=a['meshes'][a['nodes'][node]['mesh']]['primitives'][-1];g=accessor(a,ab,primitive['attributes']['POSITION'])[accessor(a,ab,primitive['indices']).reshape(-1,3)].astype(float);worldg=(g@rotation.T+matrix[:3,3])*1000;points,inv=np.unique(worldg.reshape(-1,3)/1000,axis=0,return_inverse=True);meshes.append((points+translation,inv.reshape(-1,3)))
  for piece in row['pieces']:
   if piece['kind']=='local-fitting':continue
   target=np.array(piece['vertices_mm']).mean(0)
   pt=target*.001@rotation.T+matrix[:3,3]
   for label,localdir in [('front',[0,0,1]),('back',[0,0,-1]),('above',[0,1,0]),('oblique',[.2,1,.4])]:
    direction=np.array(localdir,float)@rotation.T;direction/=np.linalg.norm(direction);far=pt*1000-direction*2000;distance=ray_mesh(far,direction,worldg);assert distance is not None
    hit=far+direction*distance;origin=(hit-direction*150)/1000+translation;quat=Rotation.align_vectors([direction],[[1,0,0]])[0].as_quat();cases.append(dict(label=f"node{node}_{piece['label']}_{label}",origin=origin.tolist(),rotation_wxyz=[quat[3],*quat[:3]],direction=direction.tolist(),entry_m=.15))
 text=['MESHES '+str(len(meshes))]
 for vertices,triangles in meshes:
  text.append('M '+str(len(vertices))+' '+str(len(triangles)));text.extend(' '.join(format(float(v),'.17g')for v in pt)for pt in vertices);text.extend(' '.join(str(int(v))for v in t)for t in triangles)
 text.append('SHOTS '+str(len(cases)))
 for case in cases:text.append('S '+case['label']+' '+' '.join(format(float(x),'.17g')for x in case['origin']+case['rotation_wxyz']+case['direction']+[case['entry_m']]))
 (OUT/'mesh-ccd-fixture.txt').write_text('\n'.join(text)+'\n');(OUT/'mesh-ccd-cases.json').write_text(json.dumps(cases,indent=2)+'\n');(OUT/'mesh-ccd-placement.json').write_text(json.dumps(dict(manifest=str(manifest_path),manifest_sha256=hub.scan.digest(manifest_path),source_to_flu_translation_m=translation.tolist()),indent=2)+'\n');print('Generated',len(cases),'trajectories for',len(cases)*4,'real-trimesh CCD shots.')
if __name__=='__main__':main()
