"""Inspect explicit arm housing axes; never infer ownership across part nodes."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-box-primitive-candidates'))
import scan
OUT=ROOT/'out/rmuc2027-core-arm-proxies'
AXES=[np.array(x,float)for x in [[0,1,0],[-.342,0,.9397],
    [.2158972245,.9732489637,.0785801694],[.7398526,-.61648496,.26937785],
    [.0885,.9659,-.2432],[-.009,-.2588,.9659]]]
AXES=[a/np.linalg.norm(a)for a in AXES]

def circles(g,axis):
    p=np.unique(g.reshape(-1,3),axis=0)
    u=np.cross(axis,[1.,.123,.456]);u/=np.linalg.norm(u);v=np.cross(axis,u)
    q=np.column_stack([p@u,p@v]);rng=np.random.default_rng(42);best=[]
    for _ in range(1800):
        tri=q[rng.choice(len(q),3,replace=False)];aa=2*(tri[1:]-tri[0])
        if abs(np.linalg.det(aa))<1e-8:continue
        c=np.linalg.solve(aa,np.sum(tri[1:]**2,axis=1)-np.sum(tri[0]**2));r=np.linalg.norm(tri[0]-c)
        if not 25<r<105:continue
        mask=abs(np.linalg.norm(q-c,axis=1)-r)<.15
        if mask.sum()>=25:best.append((int(mask.sum()),c,r))
    best.sort(key=lambda x:-x[0]);chosen=[]
    for count,c,r in best:
        if any(np.linalg.norm(c-cc)<1 and abs(r-rr)<1 for _,cc,rr in chosen):continue
        chosen.append((count,c,r))
        if len(chosen)==3:break
    output=[]
    for count,c,r in chosen:
        mask=abs(np.linalg.norm(q-c,axis=1)-r)<.15
        opt=least_squares(lambda x:np.linalg.norm(q[mask]-x[:2],axis=1)-x[2],np.r_[c,r])
        c=opt.x[:2];r=float(opt.x[2]);mask=abs(np.linalg.norm(q-c,axis=1)-r)<.2;z=p[mask]@axis
        output.append(dict(witness_vertices=int(mask.sum()),center_mm=(c[0]*u+c[1]*v+axis*(z.min()+z.max())/2).tolist(),
            axis=axis.tolist(),radius_mm=r,length_mm=float(np.ptp(z)),axial_bounds_mm=[float(z.min()),float(z.max())]))
    return output

def main():
    ref=json.loads(scan.REF.read_text());source=Path(ref['roles']['collision']['assets']['tech-core']['path'])
    assert scan.digest(source)==ref['roles']['collision']['assets']['tech-core']['sha256']
    doc,components,nodes=scan.load_nodes(source);rows={}
    for ni in [5,18,22,25,30,37]:
        rows[str(ni)]=[]
        for ai,axis in enumerate(AXES):
            fits=circles(nodes[ni],axis);rows[str(ni)].append(fits)
            print(ni,ai,[(f['witness_vertices'],round(f['radius_mm'],2),round(f['length_mm'],2))for f in fits],flush=True)
    (OUT/'circle-research.json').write_text(json.dumps(dict(source=str(source),sha256=scan.digest(source),axes=[a.tolist()for a in AXES],nodes=rows),indent=2)+'\n')

if __name__=='__main__':main()
