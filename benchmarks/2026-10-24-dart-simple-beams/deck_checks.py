"""Matched world-vertical support rays on the retained central Dart deck."""
import json
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from export import OUT,hub

def locator(g):
 pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(g.reshape(-1,3).astype(float),deep=True));cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(g),3),np.arange(len(g)*3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(pts);poly.SetPolys(cells);loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();return loc

def main():
 r=json.loads((OUT/'verification.json').read_text());_,_,old=hub.scan.load_nodes(Path(r['source_collision']));_,_,new=hub.scan.load_nodes(Path(r['candidate_collision']));rows=[]
 for record in r['records']:
  node=record['node'];matrix=np.array(record['world_matrix']);local=np.array([[x,-52.,z]for x in np.linspace(-250,250,21)for z in np.linspace(-300,600,37)]);world=local*.001@matrix[:3,:3].T+matrix[:3,3];values={}
  for stage,geo in [('source',old[node]),('candidate',new[node])]:
   loc=locator(geo);hits=[]
   for pt in world*1000:
    t=vtk.reference(0.);sub=vtk.reference(0);cell=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.];hit=loc.IntersectWithLine(pt+[0,0,2500],pt-[0,0,400],1e-7,t,point,pc,sub,cell);hits.append(float(point[2])if hit else np.nan)
   values[stage]=np.array(hits)
  before,after=values['source'],values['candidate'];both=np.isfinite(before)&np.isfinite(after);assert np.array_equal(np.isfinite(before),np.isfinite(after));delta=abs(before[both]-after[both]);assert delta.max()<1e-6
  rows.append(dict(node=node,rays=len(world),hit_state_changes=0,max_first_height_difference_mm=float(delta.max())))
 (OUT/'deck-ray-checks.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows))
if __name__=='__main__':main()
