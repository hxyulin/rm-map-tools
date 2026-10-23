"""Read original STEP topology/analytic axes without changing source geometry."""
from pathlib import Path
import sys,json,re
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from cad_document import CadDocument
h=json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_text())
result={'coordinate_contract':'Original product-local coordinates, millimetres; axes unitless','components':[]}
with CadDocument.from_step(ROOT/'source/RMUC2027_V1.0.0.stp',workers=1,expected_sha256=h['source_sha256']) as cad:
 ix,m=cad.index,cad.model
 for c in h['components']:
  if not (c['id'].startswith(('base/','outpost/','rune/','dart-station/'))):continue
  units=[('body',b) for b in c['solid_body_ids']]+[('shell',s) for ss in c['shell_ids_by_body'].values() for s in ss]
  out={'id':c['id'],'units':[]}
  for kind,u in units:
   row=ix.r(u);lo,hi,n=m.body_bbox(row)
   stack=[row];seen=set();cyl=[]
   while stack:
    r=stack.pop()
    if r in seen or r<0:continue
    seen.add(r)
    if ix.tname(r)=='CYLINDRICAL_SURFACE':
     refs=ix.refs_of(r);a=ix.r(int(refs[0]));ar=ix.refs_of(a)
     p=m.point(ix.r(int(ar[0])));d=m.point(ix.r(int(ar[1]))) if len(ar)>1 else (0,0,1)
     radius=float(re.search(rb',\s*([^,()]+)\)\s*;?$',ix.text(r)).group(1))
     if radius>=10:cyl.append({'surface_id':int(ix.ids[r]),'point_mm':p,'axis':d,'radius_mm':radius})
    stack.extend(ix.r(int(x)) for x in ix.refs_of(r))
   extra={}
   if c['id']=='dart-station/guide-rails':
    pts=np.array([m.point(ix.r(int(ix.refs_of(r)[0]))) for r in seen if ix.tname(r)=='VERTEX_POINT'])
    _,_,v=np.linalg.svd(pts-pts.mean(0),full_matrices=False)
    axis=v[0]
    if axis[1]>0:axis=-axis
    edges=[]
    for er in seen:
     if ix.tname(er)!='EDGE_CURVE':continue
     rr=ix.refs_of(er)
     ends=[m.point(ix.r(int(ix.refs_of(ix.r(int(v)))[0]))) for v in rr[:2]]
     delta=np.array(ends[1])-ends[0];length=np.linalg.norm(delta)
     if length>1000:
      delta/=length
      if delta[1]>0:delta=-delta
      edges.append({'edge_id':int(ix.ids[er]),'length_mm':float(length),'axis':delta.tolist()})
    extra={'vertex_pca_axis':axis.tolist(),'vertex_count':len(pts),'long_edge_directions':edges}
   out['units'].append({**extra,'kind':kind,'source_id':u,'bounds_mm':None if lo is None else [lo.tolist(),hi.tolist()],'cylinders':cyl})
  result['components'].append(out)
 cad.verify_source()
(ROOT/'out/rmuc2027-source-motion/analytic-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
print('Read-only source inventory complete',sum(len(c['units']) for c in result['components']))
