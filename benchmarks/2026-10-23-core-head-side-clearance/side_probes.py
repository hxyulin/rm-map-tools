"""Compare side approach rays through original recessed panel bounds."""
import json
import numpy as np
import vtk
from review import b
verify=b.p.module('side_probe_helpers',str(b.ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/verify.py'))
r=json.loads((b.OUT/'side-clearance/verification.json').read_text())
d,c,n=b.scan.load_nodes(__import__('pathlib').Path(r['source_collision']))
_,_,nn=b.scan.load_nodes(__import__('pathlib').Path(r['candidate_collision']))
def trace(loc,grid,start,end):
    t=vtk.reference(0.);sub=vtk.reference(0);cell=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.];result=[]
    for y,z in grid:
        hit=loc.IntersectWithLine([start,y,z],[end,y,z],1e-7,t,point,pc,sub,cell);result.append(float(t)*abs(end-start)if hit else np.nan)
    return np.array(result)
results=[]
for node,start,end in [(1254,-900.,-666.),(1255,-330.,-561.)]:
    bounds=[n[node].min((0,1)),n[node].max((0,1))]
    grid=np.array([[y,z]for y in np.arange(bounds[0][1]+1,bounds[1][1],2)for z in np.arange(bounds[0][2]+1,bounds[1][2],2)])
    source=trace(verify.locator(n[node]),grid,start,end)
    target=trace(verify.locator(np.concatenate([nn[node],nn[1668]])),grid,start,end)
    earlier=np.isfinite(source)&np.isfinite(target)&(target<source-.1)
    newhit=~np.isfinite(source)&np.isfinite(target)
    results.append(dict(node=node,rays=len(grid),panel_hits=int(np.isfinite(source).sum()),earlier_hits_over_0_1mm=int(earlier.sum()),new_hits=int(newhit.sum()),max_earlier_mm=float((source[earlier]-target[earlier]).max())if earlier.any()else 0))
print(results)
(b.OUT/'side-clearance/side-probes.json').write_text(json.dumps(dict(results=results,caveat='Finite side approach samples against exact panels plus new proxy, not all-pose qualification.'),indent=2)+'\n')
assert not any(x['earlier_hits_over_0_1mm']or x['new_hits']for x in results)
