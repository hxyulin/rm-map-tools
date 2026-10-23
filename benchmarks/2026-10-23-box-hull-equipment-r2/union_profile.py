from measure import *
import shapely
from shapely.geometry import Polygon

def run():
 row=next(x for x in json.loads((OUT/'screen.json').read_text())['rows'] if x['asset']=='tech-core' and x['node']==65)
 g=load_nodes(Path(row['source']))[2][65];lo,hi=g[:,:,1].min(),g[:,:,1].max();top=g[np.max(abs(g[:,:,1]-hi),axis=1)<.0001]
 shape=shapely.union_all([Polygon(h[:,[0,2]]) for h in top]);print('union',shape.geom_type,'holes',len(shape.interiors),'verts',len(shape.exterior.coords),'valid',shape.is_valid,flush=True)
 shape=shape.simplify(.2,preserve_topology=True)
 tris=shapely.constrained_delaunay_triangles(shape);polys=list(tris.geoms);print('triangles',len(polys),'holes',len(shape.interiors),flush=True)
 # Convex union only where polygon boundaries actually intersect; no near-surface welding.
 while True:
  best=None
  for i in range(len(polys)):
   for j in range(i+1,len(polys)):
    if not polys[i].intersects(polys[j]):continue
    union=polys[i].union(polys[j])
    if union.geom_type!='Polygon' or len(union.interiors):continue
    if union.convex_hull.area-union.area>1e-6:continue
    score=union.area
    if best is None or score>best[0]:best=score,i,j,union.convex_hull
  if best is None:break
  _,i,j,u=best;polys[i]=u;polys.pop(j)
 print('leaves',len(polys),flush=True)
 preview=[];leaf=[];kinds=[]
 for poly in polys:
  xz=np.asarray(poly.exterior.coords)[:-1];a=np.column_stack([xz[:,0],np.full(len(xz),lo),xz[:,1]]);b=a.copy();b[:,1]=hi;v=np.concatenate([a,b]);hu=ConvexHull(v);leaf.append(v[hu.simplices]);kinds.append('box' if len(xz)==4 and np.max(abs(np.sum((np.roll(xz,-1,axis=0)-xz)*(np.roll(xz,-2,axis=0)-np.roll(xz,-1,axis=0)),axis=1)))<.001 else 'convex-profile')
  for k in range(1,len(a)-1):preview.extend([a[[0,k,k+1]],b[[0,k+1,k]]])
 for ring in [shape.exterior,*shape.interiors]:
  xz=np.asarray(ring.coords)
  for u,v in zip(xz[:-1],xz[1:]):
   a=np.array([u[0],lo,u[1]]);b=np.array([v[0],lo,v[1]]);aa=a.copy();bb=b.copy();aa[1]=hi;bb[1]=hi;preview.extend([np.array([a,b,bb]),np.array([a,bb,aa])])
 target=np.array(preview);p=np.unique(g.reshape(-1,3),axis=0);fv=dist(p,target);rv=dist(np.unique(target.reshape(-1,3),axis=0),g);fs=dist(area_samples(g,50000,31),target);rs=dist(area_samples(target,50000,37),g)
 print('preview',len(target),'leaffaces',sum(len(l)for l in leaf),'F/R',fv.max(),rv.max(),fs.max(),rs.max(),flush=True)
 box=row['box'];c,f,half=map(np.array,[box['center_mm'],box['axes_columns'],box['half_extents_mm']]);f=f[:,np.argsort(half)[::-1]];render_pair(row,g,g,target,f,c,max(half)*1.2,'core-65-union-profile')
 np.savez_compressed(OUT/'core-65-union-profile.npz',world_triangles_mm=target,leaf_triangles_mm=np.concatenate(leaf),leaf_triangle_counts=np.array([len(x)for x in leaf]),source_triangle_indices=np.array(row['triangle_indices']),source_world_matrix_metres=np.array(row['source_world_matrix_metres']))
 rec={**row,'kind':'compact-profile-convex-compound','method':'Union of source end-face projected triangles within the same exact island; topology-preserving 0.2mm outline simplification; constrained triangulation; convex adjacent-polygon merging; extrusion to exact original thickness. No near-surface welding or owner merging.','native_leaf_count':len(leaf),'leaf_types':kinds,'native_placed_leaves':len(leaf)*row['placements'],'preview_exterior_triangles':len(target),'preview_per_leaf_triangles':sum(len(x)for x in leaf),'hypothetical_placed_exterior_savings':(len(g)-len(target))*row['placements'],'hypothetical_placed_per_leaf_preview_savings':(len(g)-sum(len(x)for x in leaf))*row['placements'],'native_placed_triangle_mesh_triangles_replaced':len(g)*row['placements'],'source_all_vertex_max_mm':float(fv.max()),'reverse_all_vertex_max_mm':float(rv.max()),'source_area_max_mm':float(fs.max()),'reverse_area_max_mm':float(rs.max()),'minimum_extent_mm':hi-lo,'max_over_thickness':float(max(fv.max(),rv.max(),fs.max(),rs.max())/(hi-lo)),'samples_each_direction':50000,'source_projected_holes':len(shape.interiors),'status':'research-shortlist if sampled errors acceptable; preserves all projected holes; source bevel/relief differs; not contact-certified','preview_files':['core-65-union-profile-before.png','core-65-union-profile-diagnostic-after.png']}
 (OUT/'union-profile.json').write_text(json.dumps(rec,indent=2)+'\n')
if __name__=='__main__':run()
