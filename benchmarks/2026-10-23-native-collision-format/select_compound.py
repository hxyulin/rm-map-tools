"""Explicit three-cylinder trial: barrel, branch and short end collar."""
import sys,json,copy
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import accessor,read_glb
out=ROOT/'out/rmuc2027-core-native-shapes';fits=json.loads((out/'joint-circle-fits.json').read_text());source=ROOT/'out/rmuc2027-installed-reference-review/reference/collision/tech-core.glb';d,b=read_glb(source);pr=d['meshes'][d['nodes'][22]['mesh']]['primitives'][0];p=accessor(d,b,pr['attributes']['POSITION']).astype(float);g=p[accessor(d,b,pr['indices']).reshape(-1,3)]
barrel=copy.deepcopy(fits[0][0]);branch=copy.deepcopy(fits[1][0]);a=np.array(barrel['axis_unit_vector']);center=np.array(barrel['center_m']);q=p-center;z=q@a;rad=np.linalg.norm(q-np.outer(z,a),axis=1)
lower=-barrel['length_m']/2;upper=float(z.max());barrel['center_m']=(center+a*(lower+upper)/2).tolist();barrel['length_m']=upper-lower
flange={'center_m':(center+a*(z.min()+lower)/2).tolist(),'axis_unit_vector':a.tolist(),'radius_m':float(rad[z<lower].max()),'length_m':float(lower-z.min()),'solid':True}
keys=['center_m','axis_unit_vector','radius_m','length_m','solid'];shapes=[{k:s[k]for k in keys} for s in [barrel,branch,flange]]
samples=np.concatenate([g.reshape(-1,3),g.mean(1),(g[:,0]+g[:,1])/2,(g[:,1]+g[:,2])/2,(g[:,2]+g[:,0])/2]);values=[]
for s in shapes:
 q=samples-s['center_m'];axis=np.array(s['axis_unit_vector']);zz=q@axis;rr=np.linalg.norm(q-np.outer(zz,axis),axis=1);dd=np.column_stack([rr-s['radius_m'],abs(zz)-s['length_m']/2]);values.append(np.linalg.norm(np.maximum(dd,0),axis=1)+np.minimum(dd.max(1),0))
v=np.min(values,axis=0);metrics={'samples':len(v),'source_samples_outside_union_max_mm':max(0,float(v.max())*1000),'outside_union_over_1mm':int(sum(v>.001)),'note':'Signed distance to solid union includes intentional filling of internal voids. Forward exterior containment samples only; no clearance or reverse silhouette certificate.'}
r=json.loads((ROOT/'rules/collision-shapes-tech-core-trial.json').read_text());r['replacements'][0].pop('cylinder');r['replacements'][0]['cylinders']=shapes;r['replacements'][0]['review_status']='three_cylinder_profile_prototype_not_contact_approved'
(ROOT/'rules/collision-shapes-tech-core-compound-trial.json').write_text(json.dumps(r,indent=2)+'\n');(out/'compound-fit-check.json').write_text(json.dumps(metrics,indent=2)+'\n');print(json.dumps(metrics,indent=2))
