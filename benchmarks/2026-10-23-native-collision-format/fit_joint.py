"""Inspect perpendicular source-supported cylinder sections of joint node22."""
import sys,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import accessor,read_glb
OUT=ROOT/'out/rmuc2027-core-native-shapes'
rule=json.loads((ROOT/'rules/collision-shapes-tech-core-trial.json').read_text());source=ROOT/'out/rmuc2027-installed-reference-review/reference/collision/tech-core.glb'
d,b=read_glb(source);pr=d['meshes'][d['nodes'][22]['mesh']]['primitives'][0];p=np.unique(accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000,axis=0)
a=np.array(rule['replacements'][0]['cylinder']['axis_unit_vector']);axes=[a,-np.load(ROOT/'out/rmuc2027-core-collision-manual/axis-17.npz')['axis']];rng=np.random.default_rng(42)
results=[]
main=axes[0];base=p.mean(0);proj=p-base;radial=proj-np.outer(proj@main,main);branch_mask=np.linalg.norm(radial,axis=1)>90
for ai,a in enumerate(axes):
 u=np.cross(a,[1.,.123,.456]);u/=np.linalg.norm(u);v=np.cross(a,u);q=np.column_stack([p@u,p@v]);best=[]
 for k in range(1600):
  pool=q if ai==0 else q[branch_mask]
  tri=pool[rng.choice(len(pool),3,replace=False)];aa=2*(tri[1:]-tri[0]);rhs=np.sum(tri[1:]**2,axis=1)-sum(tri[0]**2)
  if abs(np.linalg.det(aa))<1e-8:continue
  c=np.linalg.solve(aa,rhs);r=np.linalg.norm(tri[0]-c)
  if not 20<r<150:continue
  residual=abs(np.linalg.norm(q-c,axis=1)-r);mask=residual<.1
  if mask.sum()<12:continue
  best.append((int(mask.sum()),c,r))
 best.sort(key=lambda x:-x[0]);chosen=[]
 for count,c,r in best:
  if any(np.linalg.norm(c-cc)<.1 and abs(r-rr)<.1 for _,cc,rr in chosen):continue
  chosen.append((count,c,r))
  if len(chosen)==10:break
 output=[]
 for count,c,r in chosen:
  mask=abs(np.linalg.norm(q-c,axis=1)-r)<.1;z=p[mask]@a
  center=c[0]*u+c[1]*v+(z.min()+z.max())/2*a
  output.append(dict(count=count,center_m=(center/1000).tolist(),axis_unit_vector=a.tolist(),radius_m=float(r/1000),length_m=float(np.ptp(z)/1000),solid=True,axial_bounds_mm=[float(z.min()),float(z.max())]))
 results.append(output)
print(json.dumps(results,indent=2));(OUT/'joint-circle-fits.json').write_text(json.dumps(results,indent=2)+'\n')
