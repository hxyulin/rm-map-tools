"""Source-independent, separated static CCD fixtures for every new solid/profile."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from inventory import ROOT,OUT,hub
from gltf_scene import read_glb,accessor,scene_nodes

def ray_mesh(origin,direction,g):
 e1=g[:,1]-g[:,0];e2=g[:,2]-g[:,0];h=np.cross(np.broadcast_to(direction,e2.shape),e2);det=np.einsum('ij,ij->i',e1,h);valid=abs(det)>1e-10;inv=np.zeros(len(det));inv[valid]=1/det[valid];delta=origin-g[:,0];u=inv*np.einsum('ij,ij->i',delta,h);q=np.cross(delta,e1);v=inv*(q@direction);t=inv*np.einsum('ij,ij->i',e2,q);valid&=(u>=-1e-7)&(v>=-1e-7)&(u+v<=1+1e-7)&(t>=0)
 return float(t[valid].min())if valid.any()else None

def main():
 meshes=[];cases=[];placements=[]
 for asset_index,asset in enumerate(['outpost','rune']):
  r=json.loads((OUT/f'{asset}-verification.json').read_text());d,b=read_glb(Path(r['candidate_collision']));world={i:w for i,w,parent in scene_nodes(d)}
  for row in r['records']:
   node=row['node'];p=d['meshes'][d['nodes'][node]['mesh']]['primitives'][-1];local=accessor(d,b,p['attributes']['POSITION'])[accessor(d,b,p['indices']).reshape(-1,3)].astype(float)*1000;w=world[node];g=local@w[:3,:3].T+w[:3,3]*1000
   # Separate each owner by 5m and raise it above world retirement limits.
   shift=np.array([len(meshes)*5000.,0.,2000.])-g.mean((0,1));g+=shift
   vertices,inv=np.unique(g.reshape(-1,3)/1000,axis=0,return_inverse=True);meshes.append((vertices,inv.reshape(-1,3)));placements.append(dict(asset=asset,node=node,source_frame_fixture_translation_mm=shift.tolist()))
   offset=0
   for k,piece in enumerate(row['pieces']):
    count=piece['proxy_triangles'];geo=g[offset:offset+count];offset+=count
    # Aim through the centroid of the largest actual face, not a hole center.
    area=np.linalg.norm(np.cross(geo[:,1]-geo[:,0],geo[:,2]-geo[:,0]),axis=1);tri=geo[area.argmax()];target=tri.mean(0);normal=np.cross(tri[1]-tri[0],tri[2]-tri[0]);normal/=np.linalg.norm(normal);tangent=tri[1]-tri[0];tangent/=np.linalg.norm(tangent)
    dirs=[('front',normal),('reverse',-normal)]
    if asset=='rune':dirs += [('oblique',normal+.3*tangent),('reverse-oblique',-normal+.3*tangent)]
    for label,direction in dirs:
     direction=direction/np.linalg.norm(direction);far=target-direction*2000;distance=ray_mesh(far,direction,g);assert distance is not None;hit=far+direction*distance;origin=(hit-direction*150)/1000;quat=Rotation.align_vectors([direction],[[1,0,0]])[0].as_quat();cases.append(dict(label=f'{asset}_node{node}_piece{k}_{label}',origin=origin.tolist(),rotation_wxyz=[quat[3],*quat[:3]],direction=direction.tolist(),entry_m=.15))
 text=['MESHES '+str(len(meshes))]
 for vertices,triangles in meshes:
  text.append('M '+str(len(vertices))+' '+str(len(triangles)));text.extend(' '.join(format(float(v),'.17g')for v in p)for p in vertices);text.extend(' '.join(str(int(v))for v in t)for t in triangles)
 text.append('SHOTS '+str(len(cases)))
 for case in cases:text.append('S '+case['label']+' '+' '.join(format(float(x),'.17g')for x in case['origin']+case['rotation_wxyz']+case['direction']+[case['entry_m']]))
 (OUT/'mesh-ccd-fixture.txt').write_text('\n'.join(text)+'\n');(OUT/'mesh-ccd-cases.json').write_text(json.dumps(cases,indent=2)+'\n');(OUT/'mesh-ccd-placement.json').write_text(json.dumps(dict(placements=placements,scope='Separated static owner fixtures; no actual field placement or spinning-body integration claim.'),indent=2)+'\n');print('Generated',len(cases)*4,'shots against',len(meshes),'actual meshes.')
if __name__=='__main__':main()
