"""Generate ignored geometric fixtures for native projectile CCD, no CAD in Rust."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from cover import OUT,PREVIOUS,p,scan

def entry(origin,direction,eq,length=2500):
 a=eq[:,:3]@direction;b=eq[:,:3]@origin+eq[:,3];parallel=abs(a)<1e-12
 if (b[parallel]>0).any():return None
 lo=max(0.,float(np.max(-b[a<0]/a[a<0],initial=0.)));hi=min(length,float(np.min(-b[a>0]/a[a>0],initial=length)))
 return lo if lo<=hi else None

def main():
 r=json.loads((OUT/'verification.json').read_text());_,c,n=scan.load_nodes(Path(r['source_collision']));recipe=json.loads(Path(r['native_review']).read_text());assign=json.loads(Path(r['coverage_assignments']).read_text());cases=[];eqs=[];vertices=[]
 for part in recipe['native_parts']:
  s=part['shape'];points=np.array(s['vertices_local_m'])*1000+np.array(s['pose']['translation_m'])*1000;vertices.append(points/1000);eqs.append(ConvexHull(points).equations)
 for definition in r['definitions']:
  bank=definition['bank'];frame=np.array(definition['frame_columns']);pivot=np.array(definition['pivot_mm']);phase=np.deg2rad(definition['spoke_phase_deg']);parts=[x for x in recipe['native_parts']if x['source_group']==bank+'-fixed-hub']
  for k in range(5):
   triangles=np.concatenate([n[int(i)][np.array(labels)==k]for i,labels in assign[bank].items()if(np.array(labels)==k).any()]);centroids=triangles.mean(1);local=(centroids-pivot)@frame;radius=np.linalg.norm(local[:,:2],axis=1);targets=[('front',centroids[local[:,2].argmax()if bank=='bank-a'else local[:,2].argmin()]),('tip',centroids[radius.argmax()]),('root',centroids[radius.argmin()])]
   radial=np.array([np.cos(phase+k*2*np.pi/5),np.sin(phase+k*2*np.pi/5),0])@frame.T;axis=frame[:,2]
   for target_name,pt in targets:
    for direction_name,di in [('forward',axis),('reverse',-axis),('oblique',axis+.5*radial)]:
     direction=di/np.linalg.norm(di);far=pt-direction*1000;distance=min((x for eq in eqs if(x:=entry(far,direction,eq))is not None),default=None);assert distance is not None
     hit=far+direction*distance;origin=(hit-direction*150)/1000;quat=Rotation.align_vectors([direction],[[1,0,0]])[0].as_quat();cases.append(dict(label=f'{bank}_spoke{k}_{target_name}_{direction_name}',origin=origin.tolist(),rotation_wxyz=[quat[3],*quat[:3]],direction=direction.tolist(),entry_m=.15))
  # Normal shots at the deliberately filled center.
  for sign in [-1,1]:
   direction=frame[:,2]*sign;pt=pivot;far=pt-direction*1000;distance=min(x for eq in eqs if(x:=entry(far,direction,eq))is not None);hit=far+direction*distance;origin=(hit-direction*150)/1000;quat=Rotation.align_vectors([direction],[[1,0,0]])[0].as_quat();cases.append(dict(label=f'{bank}_filled_center_{sign}',origin=origin.tolist(),rotation_wxyz=[quat[3],*quat[:3]],direction=direction.tolist(),entry_m=.15))
 text=['HULLS '+str(len(vertices))]
 for points in vertices:text.append('H '+str(len(points)));text.extend(' '.join(format(float(x),'.17g')for x in row)for row in points)
 text.append('SHOTS '+str(len(cases)))
 for case in cases:text.append('S '+case['label']+' '+' '.join(format(float(x),'.17g')for x in case['origin']+case['rotation_wxyz']+case['direction']+[case['entry_m']]))
 path=OUT/'native-ccd-fixture.txt';path.write_text('\n'.join(text)+'\n');(OUT/'native-ccd-cases.json').write_text(json.dumps(cases,indent=2)+'\n');print('Generated',len(cases),'trajectories x4 calibers/speeds =',len(cases)*4,'shots; fixture',path)
if __name__=='__main__':main()
