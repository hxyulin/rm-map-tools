"""Connected-source profile selection and baseline surface ownership checks."""
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from cad_dense_lod import surface_samples
from mesh_quality import distances

def components(g):
 p,inv=np.unique(np.round(g.reshape(-1,3)/.02).astype(np.int64),axis=0,return_inverse=True);t=inv.reshape(-1,3);e=np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]);_,labels=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(p),len(p))).tocsr(),directed=False)
 return labels[t[:,0]]
def nearest_labels(g,samples,labels):
 import vtk
 from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
 p=g.reshape(-1,3);t=np.arange(len(p)).reshape(-1,3);pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(p,deep=True));cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(t),3),t]).astype(np.int64).ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(pts);poly.SetPolys(cells);loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();closest=[0.,0.,0.];cell,sub,d2=vtk.reference(0),vtk.reference(0),vtk.reference(0.);result=[]
 for p in samples:loc.FindClosestPoint(p,closest,cell,sub,d2);result.append(labels[int(cell)])
 return np.array(result)
def rebuild(g,cg,profile,allowance=3):
 labels=components(g);ct=np.arange(cg.size//3).reshape(-1,3);samples=surface_samples(cg.reshape(-1,3),ct);owners=nearest_labels(g,samples.reshape(-1,3),labels).reshape(-1,7);mixed=owners.min(1)!=owners.max(1);blocked=set(owners[mixed].ravel());owner=owners[:,0];out=[];patches=[];keep=np.ones(len(cg),bool)
 for k in np.unique(labels):
  if k in blocked:continue
  part=g[labels==k];cost=int((owner==k).sum())
  if cost<40 or len(part)<40:continue
  _,_,v=np.linalg.svd(part.reshape(-1,3)-part.reshape(-1,3).mean(0),full_matrices=False);best=None
  for normal in [*v,*np.eye(3)]:
   try:
    q,t,proof=profile(part,normal)
    if len(t)>=cost:continue
    p=part.reshape(-1,3);f=np.arange(len(p)).reshape(-1,3);fw=distances(surface_samples(p,f).reshape(-1,3),q,t);rv=distances(surface_samples(q,t).reshape(-1,3),p,f);err=float(max(fw.max(),rv.max()))
    if err>allowance:continue
    # Independently protect the accepted coverage of this selected subset.
    old=cg[owner==k];bf=distances(surface_samples(old.reshape(-1,3),np.arange(old.size//3).reshape(-1,3)).reshape(-1,3),q,t)
    if bf.max()>allowance:continue
    row={**proof,'source_connected_piece':int(k),'source_triangles':len(part),'baseline_triangles':cost,'output_triangles':len(t),'forward_max_mm':float(fw.max()),'reverse_max_mm':float(rv.max()),'baseline_forward_max_mm':float(bf.max()),'samples':len(fw)+len(rv)+len(bf),'maximum_allowance_mm':allowance,'source_bounds_mm':[part.min((0,1)).tolist(),part.max((0,1)).tolist()]}
    if best is None or len(t)<len(best[1]):best=q,t,row
   except (ValueError,RuntimeError):continue
  if best:
   q,t,row=best;out.append(row);patches.append(q[t]);keep[owner==k]=False
 return np.concatenate([cg[keep],*patches]),out
