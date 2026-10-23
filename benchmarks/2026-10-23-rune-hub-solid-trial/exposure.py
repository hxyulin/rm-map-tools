"""Finite two-sided hub-center disk exposure screen, before/after collision."""
import json
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from hub import OUT as ROOT_OUT,scan,p
import sys
OUT=ROOT_OUT/('open-centers'if '--open-centers'in sys.argv else'clearance-screened')
def locator(g):
 pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(g.reshape(-1,3).astype(float),deep=True));cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(g),3),np.arange(len(g)*3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(pts);poly.SetPolys(cells);loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();return loc
r=json.loads((OUT/'verification.json').read_text());d,c,n=scan.load_nodes(Path(r['source_collision']));_,_,new=scan.load_nodes(Path(r['candidate_collision']));rows=[]
for disk in [272,426]:
 bank='bank-a'if disk==272 else'bank-b';ids=sorted(i for i in n if c[i]==f'rune/banks/{bank}/hub-cluster');points=scan.area_samples(n[disk],1000,seed=274);_,_,vt=np.linalg.svd(n[disk].reshape(-1,3)-n[disk].reshape(-1,3).mean(0),full_matrices=False);normal=vt[-1]
 for sign in [-1,1]:
  lengths={};hitowners={}
  for name,geos in [('source',n),('candidate',new)]:
   g=np.concatenate([geos[i]for i in ids]);owners=np.concatenate([np.full(len(geos[i]),i)for i in ids]);loc=locator(g);result=[];who=[]
   for pt in points:
    t=vtk.reference(0.);cell=vtk.reference(0);sub=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.];hit=loc.IntersectWithLine(pt+sign*normal*600,pt-sign*normal*50,1e-7,t,point,pc,sub,cell);result.append(float(t)*650 if hit else np.nan);who.append(int(owners[int(cell)])if hit else-1)
   lengths[name]=np.array(result);hitowners[name]=np.array(who)
  both=np.isfinite(lengths['source'])&np.isfinite(lengths['candidate']);delta=lengths['source'][both]-lengths['candidate'][both];was_disk=hitowners['source']==disk;changed=(hitowners['candidate']!=disk)&was_disk
  rows.append(dict(disk=disk,normal_sign=sign,rays=len(points),source_disk_first_hits=int(was_disk.sum()),source_disk_hits_now_other_owner=int(changed.sum()),candidate_earlier_over_2mm=int((delta>2).sum()),max_earlier_mm=float(delta.max()),normal=normal.tolist()))
print(json.dumps(rows));(OUT/'disk-exposure-screen.json').write_text(json.dumps(rows,indent=2)+'\n')
