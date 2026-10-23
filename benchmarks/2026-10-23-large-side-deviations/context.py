"""Source-only feature diagnostic views and projection checks, no proxy fill."""
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import vtk
from investigate import OUT,load_nodes
from panel_trial import render

def run():
 r=json.loads((OUT/'measurements.json').read_text());records=[];cache={}
 for asset,ni,pi in [('base',8,3),('outpost',10,0),('outpost',14,2),('outpost',25,0),('arena-static',354,0)]:
  n=next(x for x in r['nodes']if x['asset']==asset and x['node']==ni);patch=n['patches'][pi]
  if n['source']not in cache:cache[n['source']]=load_nodes(Path(n['source']))[2]
  g=cache[n['source']][ni];ids=np.array(patch['triangle_indices']);h=g[ids];f=np.array(patch['fit']['axes_columns']);center=np.array(patch['fit']['center_mm']);normal=f[:,2]
  if normal@(center-g.mean((0,1)))<0:normal=-normal
  direction=normal+.4*f[:,0]+.25*f[:,1];direction/=np.linalg.norm(direction);cam=vtk.vtkCamera();cam.SetPosition(*(center+direction*5000));cam.SetFocalPoint(*center);cam.SetViewUp(*f[:,1]);cam.ParallelProjectionOn();cam.SetParallelScale(max(patch['fit']['spans_mm'][:2])*.45)
  bounds=tuple(v for pair in zip(g.min((0,1)),g.max((0,1)))for v in pair);name=f'{asset}-{ni}-patch-{pi}-context.png';render(np.delete(g,ids,axis=0),h,cam,bounds,name)
  records.append(dict(asset=asset,node=ni,patch_index=pi,path=name,scope='Source selected owner only; grey unselected triangles and orange slab patch. Other owners absent.'))
 # Projection fold/cancellation is a rejection signal, not proof when absent.
 for n in r['nodes']:
  if n['source']not in cache:cache[n['source']]=load_nodes(Path(n['source']))[2]
  g=cache[n['source']][n['node']]
  for patch in n['patches']:
   h=g[patch['triangle_indices']];q=h@np.array(patch['fit']['axes_columns'])[:,:2];cr=(q[:,1,0]-q[:,0,0])*(q[:,2,1]-q[:,0,1])-(q[:,1,1]-q[:,0,1])*(q[:,2,0]-q[:,0,0]);patch['projection_check']=dict(absolute_projected_area_mm2=float(abs(cr).sum()/2),signed_projected_area_magnitude_mm2=float(abs(cr.sum())/2),orientation_cancellation_fraction=float(1-abs(cr.sum())/max(abs(cr).sum(),1e-30)),note='Cancellation indicates fold/overlap/inconsistent winding; zero does not certify no overlap. Patch boundaries may be slab cuts rather than native openings.')
 (OUT/'measurements.json').write_text(json.dumps(r,indent=2)+'\n');(OUT/'context-renders.json').write_text(json.dumps(records,indent=2)+'\n')
if __name__=='__main__':run()
