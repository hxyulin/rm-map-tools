"""Optional Dart side profile: finite measurements, no seam/contact adoption."""
import sys,json
sys.dont_write_bytecode=True
import numpy as np
import vtk
from pathlib import Path
from investigate import OUT,load_nodes,topology,area_samples,distances
from panel_trial import render

def loop(h):
 p,t,_,_=topology(h);edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);e,c=np.unique(edges,axis=0,return_counts=True);b=e[c==1];graph={int(i):[]for i in np.unique(b)}
 for u,v in b:graph[int(u)].append(int(v));graph[int(v)].append(int(u))
 assert all(len(v)==2 for v in graph.values());start=min(graph);seq=[start];cur=start;prev=None
 while True:
  nxt=next(i for i in graph[cur]if i!=prev)
  if nxt==start:break
  seq.append(nxt);prev,cur=cur,nxt
 assert len(seq)==len(graph)
 return p[seq]

def rdp(points,tol):
 if len(points)<=2:return points
 d=points[-1]-points[0];alpha=np.clip((points-points[0])@d/max(d@d,1e-30),0,1);dist=np.linalg.norm(points-points[0]-alpha[:,None]*d,axis=1);i=np.argmax(dist)
 if dist[i]<=tol:return points[[0,-1]]
 return np.concatenate([rdp(points[:i+1],tol)[:-1],rdp(points[i:],tol)])

def triangulate(xyz,fit):
 q=xyz@np.asarray(fit['axes_columns']);poly=vtk.vtkPolygon();poly.GetPointIds().SetNumberOfIds(len(q));poly.GetPoints().SetNumberOfPoints(len(q))
 for i,v in enumerate(q):poly.GetPointIds().SetId(i,i);poly.GetPoints().SetPoint(i,float(v[0]),float(v[1]),0.)
 ids=vtk.vtkIdList();pts=vtk.vtkPoints();assert poly.Triangulate(0,ids,pts)
 t=np.array([ids.GetId(i)for i in range(ids.GetNumberOfIds())]).reshape(-1,3);return t

def run():
 r=json.loads((OUT/'measurements.json').read_text());n=next(x for x in r['nodes']if x['asset']=='arena-static');g=load_nodes(Path(n['source']))[2][354];results=[]
 for pi in [6,7]:
  patch=n['patches'][pi];ids=np.array(patch['triangle_indices']);h=g[ids];boundary=loop(h);j=np.argmax(np.linalg.norm(boundary-boundary[0],axis=1));xyz=np.concatenate([rdp(boundary[:j+1],.5)[:-1],rdp(np.concatenate([boundary[j:],boundary[:1]]),.5)[:-1]]);t=triangulate(xyz,patch['fit']);target=xyz[t]
  def distance(points,to):return distances(points,to.reshape(-1,3),np.arange(len(to)*3).reshape(-1,3))
  fv=distance(np.unique(h.reshape(-1,3),axis=0),target);fs=distance(area_samples(h,50000,31),target);rs=distance(area_samples(target,50000,37),h)
  # Segment-sampled outline checks in both directions, separate from panel interior.
  def lines(p):return np.concatenate([p[i]*(1-np.linspace(0,1,21))[:,None]+p[(i+1)%len(p)]*np.linspace(0,1,21)[:,None]for i in range(len(p))])
  def to_lines(samples,p):
   a=p;b=np.roll(p,-1,axis=0);d=b-a;v=samples[:,None,:]-a;u=np.clip(np.einsum('nki,ki->nk',v,d)/np.maximum((d*d).sum(1),1e-30),0,1);return np.linalg.norm(v-u[:,:,None]*d,axis=2).min(1)
  outline_f=to_lines(lines(boundary),xyz);outline_r=to_lines(lines(xyz),boundary)
  f=np.array(patch['fit']['axes_columns']);q=h@f[:,:2];cross=(q[:,1,0]-q[:,0,0])*(q[:,2,1]-q[:,0,1])-(q[:,1,1]-q[:,0,1])*(q[:,2,0]-q[:,0,0]);projected_sum=abs(cross).sum()/2;projected_signed=abs(cross.sum())/2
  rec=dict(asset='arena-static',node=354,component=n['component'],patch_index=pi,source_triangles=len(h),trial_triangles=len(t),source_boundary_vertices=len(boundary),trial_boundary_vertices=len(xyz),boundary_simplification_tolerance_mm=.5,source_all_vertex_to_trial_max_mm=float(fv.max()),source_area_mean_mm=float(fs.mean()),source_area_p99_mm=float(np.quantile(fs,.99)),source_area_sample_max_mm=float(fs.max()),trial_area_sample_max_mm=float(rs.max()),trial_area_p99_mm=float(np.quantile(rs,.99)),samples_each_direction=50000,source_outline_sample_max_mm=float(outline_f.max()),trial_outline_sample_max_mm=float(outline_r.max()),source_projected_absolute_area_mm2=float(projected_sum),source_projected_signed_area_mm2=float(projected_signed),source_triangle_indices=ids.tolist(),status='Boundary changes require adjacent-face reconstruction; not watertight drop-in or collision certified.',renders=[])
  np.savez_compressed(OUT/f'dart-profile-{pi}-trial.npz',positions_mm=xyz,triangles=t,source_triangle_indices=ids)
  center=np.array(patch['fit']['center_mm']);normal=f[:,2]
  if normal@(center-g.mean((0,1)))<0:normal=-normal
  direction=normal+.25*f[:,0]+.25*f[:,1];direction/=np.linalg.norm(direction);cam=vtk.vtkCamera();cam.SetPosition(*(center+direction*5000));cam.SetFocalPoint(*center);cam.SetViewUp(*f[:,1]);cam.ParallelProjectionOn();cam.SetParallelScale(max(patch['fit']['spans_mm'][:2])*.43)
  bounds=tuple(v for pair in zip(g.min((0,1)),g.max((0,1)))for v in pair)
  for stage,hg in [('source',h),('trial',target)]:
   name=f'dart-profile-{pi}-{stage}.png';render(np.delete(g,ids,axis=0),hg,cam,bounds,name);rec['renders'].append(dict(stage=stage,path=name))
  results.append(rec);print({k:v for k,v in rec.items()if k not in ['source_triangle_indices','renders']},flush=True)
 (OUT/'profile-trials.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':run()
