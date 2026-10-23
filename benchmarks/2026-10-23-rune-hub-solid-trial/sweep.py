"""Conservative finite moving-arm intrusion screen for fixed hub envelopes."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from hub import OUT,BINDINGS,p,scan,v
r=json.loads((OUT/'verification.json').read_text());d,c,n=scan.load_nodes(Path(r['source_collision']));bindings=json.loads(BINDINGS.read_text());recipe=json.loads(Path(r['native_review']).read_text());rows=[]
for motion in bindings['rune_motion']:
 bank='bank-a'if '.red.'in motion['id']else'bank-b';ids=[i for i in n if c[i].startswith('rune/banks/'+bank+'/arm-')];g=np.concatenate([n[i]for i in ids]);points=np.concatenate([np.unique(g.reshape(-1,3),axis=0),scan.area_samples(g,4000,seed=732)])
 axis=np.array(motion['axis']);pivot=np.array(motion['pivot_m'])*1000
 for part in recipe['native_parts']:
  if '/'+bank+'/'not in part['component_id']:continue
  i=part['source_node_index'];shape=part['shape'];verts=np.array(shape['vertices_local_m'])*1000+np.array(shape['pose']['translation_m'])*1000;eq=ConvexHull(verts).equations
  witnesses=[];by_pose=[]
  for angle in range(0,360,15):
   pts=Rotation.from_rotvec(axis*np.deg2rad(angle)).apply(points-pivot)+pivot
   mask=np.max(pts@eq[:,:3].T+eq[:,3],axis=1)<-.5
   by_pose.append(dict(angle_deg=angle,arm_samples_inside=int(mask.sum())))
   if mask.any():witnesses.append(pts[mask])
  hits=np.concatenate(witnesses)if witnesses else np.empty((0,3));dist=p.distances(hits,n[i].reshape(-1,3),np.arange(len(n[i])*3).reshape(-1,3))if len(hits)else np.array([])
  row=dict(node=i,bank=bank,arm_samples_per_pose=len(points),poses=by_pose,inside_witnesses=len(hits),inside_witnesses_over_2mm_from_source_surface=int((dist>2).sum()),max_inside_witness_distance_to_source_mm=float(dist.max())if len(dist)else 0,
   caution='A new-hull intrusion witness is a conservative rejection signal, not a proof of a newly introduced physical contact: source-solid interiors are not classified. No witness is only finite-pose evidence.')
  rows.append(row);print(i,'sweep witnesses',len(hits),'over2mm',row['inside_witnesses_over_2mm_from_source_surface'],flush=True)
(OUT/'sweep-screen.json').write_text(json.dumps(rows,indent=2)+'\n')
