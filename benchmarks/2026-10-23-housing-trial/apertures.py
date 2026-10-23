"""Fill explicitly small apertures in source planar panels, preserve broad holes."""
from collections import defaultdict
import numpy as np
import shapely as sh
from shapely.geometry import Polygon
from cad_dense_lod import surface_samples
from mesh_quality import distances

def fill(g,cg,limit=17):
 sn=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);area=np.linalg.norm(sn,axis=1);sn/=np.maximum(area[:,None],1e-30);sd=np.einsum('ij,ij->i',sn,g[:,0]);groups=defaultdict(list)
 for i,key in enumerate(np.column_stack([np.rint(sn/.0001),np.rint(sd/.02)]).astype(np.int64)):
  if area[i]>1e-8:groups[tuple(key)].append(i)
 cn=np.cross(cg[:,1]-cg[:,0],cg[:,2]-cg[:,0]);cn/=np.maximum(np.linalg.norm(cn,axis=1)[:,None],1e-30)
 keep=np.ones(len(cg),bool);patches=[];records=[];source_selected=set()
 for ids in groups.values():
  if len(ids)<8 or area[ids].sum()<20000:continue
  n=sn[ids[np.argmax(area[ids])]];o=g[ids[0],0]
  if np.abs((g[ids]-o)@n).max()>.02:continue
  x=np.cross(np.eye(3)[np.argmin(abs(n))],n);x/=np.linalg.norm(x);basis=np.array([x,np.cross(n,x)]);domain=sh.union_all(sh.polygons((g[ids]-o)@basis.T),grid_size=.001)
  if domain.geom_type not in ['Polygon','MultiPolygon'] or not domain.is_valid:continue
  replacement=[];holes=[]
  for part in sh.get_parts(domain):
   retained=[]
   for ring in part.interiors:
    h=Polygon(ring);width=float(np.ptp(np.array(ring.coords),axis=0).max())
    if width<limit and h.area>1:holes.append((h,width))
    else:retained.append(ring)
   replacement.append(Polygon(part.exterior,retained).simplify(.05,preserve_topology=True))
  if not holes:continue
  cp=(cg-o)@basis.T;depth=(cg-o)@n
  planar=np.flatnonzero(keep & (cn@n>1-1e-7) & (abs(depth).max(1)<.03))
  selected=planar[sh.covered_by(sh.polygons(cp[planar]),sh.buffer(domain,.1))]
  if not len(selected):continue
  # Remove only local aperture wall surfaces within 10mm of this panel.
  removed_walls=[]
  for h,width in holes:
   nearby=np.flatnonzero(keep & (abs(depth).max(1)<=10) & (cn@n<.99))
   inside=sh.covered_by(sh.points(cp[nearby].reshape(-1,2)),h.buffer(.1)).reshape(-1,3).all(1)
   removed_walls.extend(nearby[inside].tolist())
  triangles=sh.get_parts(sh.constrained_delaunay_triangles(sh.union_all(replacement)))
  if not len(triangles):continue
  uv=np.array([np.array(t.exterior.coords)[:3] for t in triangles]);patch=o+uv@basis;flip=np.cross(patch[:,1]-patch[:,0],patch[:,2]-patch[:,0])@n<0;patch[flip]=patch[flip][:,::-1]
  dropped=np.union1d(selected,np.array(removed_walls,dtype=np.int64)).astype(np.int64)
  if len(patch)>=len(dropped):continue
  source_selected.update(ids)
  for h,width in holes:
   local=(g-o)@basis.T;dd=(g-o)@n;nearby=np.flatnonzero(abs(dd).max(1)<=10);inside=sh.covered_by(sh.points(local[nearby].reshape(-1,2)),h.buffer(.1)).reshape(-1,3).all(1);source_selected.update(nearby[inside].tolist())
  keep[dropped]=False;patches.append(patch);records.append({'source_plane_normal':n.tolist(),'source_plane_origin_mm':o.tolist(),'filled_holes':[{'bounding_width_mm':w,'area_mm2':h.area,'center_uv_mm':list(h.centroid.coords)[0]} for h,w in holes],'baseline_triangles':len(dropped),'output_triangles':len(patch),'removed_local_wall_triangles':len(set(removed_walls)),'source_outer_outline_tolerance_mm':.05,'maximum_wall_neighborhood_mm':10})
 if not records:return cg,[]
 out=np.concatenate([cg[keep],*patches]);p=g.reshape(-1,3);t=np.arange(len(p)).reshape(-1,3);q=out.reshape(-1,3);f=np.arange(len(q)).reshape(-1,3);local=g[sorted(source_selected)];lp=local.reshape(-1,3);lt=np.arange(len(lp)).reshape(-1,3);new=np.concatenate(patches);np_=new.reshape(-1,3);nt=np.arange(len(np_)).reshape(-1,3)
 fw=distances(surface_samples(lp,lt).reshape(-1,3),q,f);rv=distances(surface_samples(np_,nt).reshape(-1,3),p,t);old=cg[~keep];bf=distances(surface_samples(old.reshape(-1,3),np.arange(old.size//3).reshape(-1,3)).reshape(-1,3),q,f)
 if max(fw.max(),rv.max(),bf.max())>10:return cg,[]
 return out,[{'operation':'source-planar-small-aperture-fill','planes':records,'source_triangles':len(g),'baseline_triangles':len(cg),'output_triangles':len(out),'forward_max_mm':float(fw.max()),'reverse_max_mm':float(rv.max()),'baseline_forward_max_mm':float(bf.max()),'samples':len(fw)+len(rv)+len(bf),'maximum_allowance_mm':10,'measurement_scope':'Changed source panels/aperture walls to full output; newly generated caps to original source; removed baseline triangles to output. Unchanged baseline remainder excluded.'}]
