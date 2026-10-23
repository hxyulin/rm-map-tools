"""Inspect exact planar source-face families without triangle-union slivers."""
import json
import numpy as np
from build import REF,OUT,domain,topology

def main():
 s=np.load(REF);g=s['positions_mm'][s['triangles']];rows=[]
 for f in np.unique(s['source_face_ids']):
  m=s['source_face_ids']==f;t=g[m];n=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);area=np.linalg.norm(n,axis=1).sum()/2
  if area<1000:continue
  r=domain(t)
  if r is None:continue
  dom,o,basis,n,err=r;rows.append({'source_face_id':int(f),'source_shell_id':int(s['source_unit_ids'][m][0]),'source_triangles':len(t),'area_mm2':float(area),'source_topology':topology(dom),'plane_error_mm':err,'normal':n.tolist(),'origin_mm':o.tolist(),'span_mm':np.ptp(t.reshape(-1,3),axis=0).tolist()})
 rows.sort(key=lambda r:r['area_mm2'],reverse=True);(OUT/'planar-discovery.json').write_text(json.dumps(rows,indent=2)+'\n');print('planar face families:',len(rows))
if __name__=='__main__':main()
