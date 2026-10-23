"""Boundary and attachment preserving local experiment; never installed/exported GLB."""
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,vtk_to_numpy
from investigate import OUT,load_nodes,topology,area_samples,distances,sha

def poly(g):
 data=vtk.vtkPolyData();points=vtk.vtkPoints();points.SetData(numpy_to_vtk(g.reshape(-1,3),deep=True));data.SetPoints(points)
 cells=vtk.vtkCellArray()
 for i in range(len(g)):
  cells.InsertNextCell(3)
  for j in range(3):cells.InsertCellPoint(i*3+j)
 data.SetPolys(cells);return data

def attachments(g,ids):
 selected={tuple(p)for p in g[ids].reshape(-1,3)};remaining={tuple(p)for p in np.delete(g,ids,axis=0).reshape(-1,3)}
 return np.array(sorted(selected & remaining))

def triangulate(h,fit,retain_points=None):
 p,t,_,_=topology(h);edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);e,c=np.unique(edges,axis=0,return_counts=True);b=e[c==1];graph={int(i):[] for i in np.unique(b)}
 for u,v in b:graph[int(u)].append(int(v));graph[int(v)].append(int(u))
 assert all(len(v)==2 for v in graph.values())
 start=min(graph);seq=[start];prev=None;cur=start
 while True:
  nxt=next(i for i in graph[cur]if i!=prev)
  if nxt==start:break
  seq.append(nxt);prev,cur=cur,nxt
 assert len(seq)==len(graph)
 xyz=p[seq];f=np.asarray(fit['axes_columns']);q=xyz@f;polygon=vtk.vtkPolygon();polygon.GetPointIds().SetNumberOfIds(len(seq));polygon.GetPoints().SetNumberOfPoints(len(seq))
 for i,v in enumerate(q):polygon.GetPointIds().SetId(i,i);polygon.GetPoints().SetPoint(i,float(v[0]),float(v[1]),0.)
 ids=vtk.vtkIdList();pts=vtk.vtkPoints();assert polygon.Triangulate(0,ids,pts)
 # Triangulate returns point ids referring to original polygon ordering.
 faces=np.array([ids.GetId(i)for i in range(ids.GetNumberOfIds())]).reshape(-1,3)
 assert len(faces)==len(seq)-2 and len(np.unique(faces))==len(seq)
 if retain_points is not None:
  for point in retain_points:
   if np.min(np.linalg.norm(xyz-point,axis=1))<1e-8:continue
   xy=xyz@f[:,:2];point_xy=point@f[:,:2];delta=xy[faces]-point_xy
   determinants=(delta[:,1,0]-delta[:,0,0])*(delta[:,2,1]-delta[:,0,1])-(delta[:,1,1]-delta[:,0,1])*(delta[:,2,0]-delta[:,0,0])
   bary=np.column_stack([(delta[:,1,0]*delta[:,2,1]-delta[:,1,1]*delta[:,2,0])/determinants,(delta[:,2,0]*delta[:,0,1]-delta[:,2,1]*delta[:,0,0])/determinants,(delta[:,0,0]*delta[:,1,1]-delta[:,0,1]*delta[:,1,0])/determinants])
   hits=np.flatnonzero(np.min(bary,axis=1)>=-1e-8);assert len(hits), 'attachment outside projected boundary'
   new_id=len(xyz);xyz=np.concatenate([xyz,point[None,:]]);new_faces=[]
   for hit in hits:
    face=faces[hit];zero=np.flatnonzero(abs(bary[hit])<1e-8)
    if len(zero)==0:
     new_faces.extend([[face[0],face[1],new_id],[face[1],face[2],new_id],[face[2],face[0],new_id]])
    elif len(zero)==1:
     k=int(zero[0]);u,v=face[(k+1)%3],face[(k+2)%3];w=face[k];new_faces.extend([[u,new_id,w],[new_id,v,w]])
    else:raise ValueError('distinct attachment projects onto an existing vertex')
   faces=np.concatenate([np.delete(faces,hits,axis=0),np.array(new_faces)])
 source_normal=np.cross(h[:,1]-h[:,0],h[:,2]-h[:,0]).sum(0)
 trial=xyz[faces];trial_normal=np.cross(trial[:,1]-trial[:,0],trial[:,2]-trial[:,0]).sum(0)
 if source_normal@trial_normal<0:faces=faces[:,[0,2,1]]
 return xyz,faces

def render(g,highlight,camera,bounds,name):
 renderer=vtk.vtkRenderer();renderer.SetBackground(.955,.962,.975)
 for geom,color in [(g,(.63,.68,.74)),(highlight,(.98,.47,.12))]:
  mapper=vtk.vtkPolyDataMapper();mapper.SetInputData(poly(geom));actor=vtk.vtkActor();actor.SetMapper(mapper);actor.GetProperty().SetColor(*color);actor.GetProperty().SetAmbient(.35);actor.GetProperty().SetDiffuse(.65);renderer.AddActor(actor)
 window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(1100,800);window.AddRenderer(renderer);renderer.SetActiveCamera(camera);renderer.ResetCameraClippingRange(*bounds);window.Render()
 capture=vtk.vtkWindowToImageFilter();capture.SetInput(window);capture.Update();writer=vtk.vtkPNGWriter();writer.SetFileName(str(OUT/name));writer.SetInputConnection(capture.GetOutputPort());writer.Write();window.Finalize()

def run():
 r=json.loads((OUT/'measurements.json').read_text());n=next(x for x in r['nodes']if x['asset']=='base'and x['node']==13);patch=n['patches'][2];ids=np.array(patch['triangle_indices']);g=load_nodes(Path(n['source']))[2][13];h=g[ids];xyz,t=triangulate(h,patch['fit'],attachments(g,ids));target=xyz[t];rest=np.delete(g,ids,axis=0)
 np.savez_compressed(OUT/'base-housing-panel-trial.npz',positions_mm=xyz,triangles=t,source_triangle_indices=ids)
 def distance(points,to):return distances(points,to.reshape(-1,3),np.arange(len(to)*3).reshape(-1,3))
 fv=distance(np.unique(h.reshape(-1,3),axis=0),target);rv=distance(xyz,h);fs=distance(area_samples(h,50000,31),target);rs=distance(area_samples(target,50000,37),h)
 rec=dict(asset='base',node=13,source_name=n['name'],source_sha256=n['sha256'],patch_index=2,source_triangles=len(h),trial_triangles=len(t),source_triangle_indices=ids.tolist(),source_all_vertex_to_trial_max_mm=float(fv.max()),trial_all_vertex_to_source_max_mm=float(rv.max()),source_area_sample_max_mm=float(fs.max()),source_area_p99_mm=float(np.quantile(fs,.99)),source_area_mean_mm=float(fs.mean()),trial_area_sample_max_mm=float(rs.max()),trial_area_p99_mm=float(np.quantile(rs,.99)),samples_each_direction=50000,boundary_vertices_kept=12,total_retained_vertices=len(xyz),shared_attachment_vertices_kept=len(attachments(g,ids)),boundary_position_error_mm=0.,hypothetical_placed_savings=(len(h)-len(t))*n['placements'],status='Local research panel only; preserves selected seam positions. No continuous bound, solid/contact/pose validation, native export or adoption.',renders=[])
 fit=patch['fit'];f=np.array(fit['axes_columns']);center=np.array(fit['center_mm']);long=max(fit['spans_mm'][:2]);normal=f[:,2]
 # Face the external side of housing by choosing away from owner centroid.
 if normal@(center-g.mean((0,1)))<0:normal=-normal
 for view,direction in [('normal',normal),('oblique',normal+.65*f[:,0]+.35*f[:,1])]:
  direction/=np.linalg.norm(direction)
  for scope,scale in [('local',.46),('whole',1.5)]:
   cam=vtk.vtkCamera();cam.SetPosition(*(center+direction*2500));cam.SetFocalPoint(*center);cam.SetViewUp(*f[:,1]);cam.ParallelProjectionOn();cam.SetParallelScale(long*scale)
   bounds=tuple(v for pair in zip(g.min((0,1)),g.max((0,1)))for v in pair)
   for stage,hg in [('source',h),('trial',target)]:
    name=f'base-housing-{scope}-{view}-{stage}.png';render(rest,hg,cam,bounds,name);rec['renders'].append(dict(scope=scope,view=view,stage=stage,path=name))
 (OUT/'panel-trial.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps({k:v for k,v in rec.items()if k not in ['source_triangle_indices','renders']},indent=2))
if __name__=='__main__':run()
