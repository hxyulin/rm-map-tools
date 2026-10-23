from measure import *

def run():
 row=next(x for x in json.loads((OUT/'screen.json').read_text())['rows'] if x['asset']=='tech-core' and x['node']==65)
 g=load_nodes(Path(row['source']))[2][65];p,t,lab,n=topology(g);lo,hi=p[:,1].min(),p[:,1].max();mask=np.max(abs(g[:,:,1]-hi),axis=1)<.0001;top=g[mask];q,faces,_,_=topology(top);xy=q[:,[0,2]]
 print('top',len(top),'points',len(q),'thickness',hi-lo,flush=True)
 polygons=[list(f) for f in faces];merged=True
 # Merge exactly shared polygon edges only, no bridging, planar convex hull area test.
 while merged:
  merged=False;edge_map={}
  for i,poly in enumerate(polygons):
   for a,b in zip(poly,poly[1:]+poly[:1]):edge_map.setdefault(tuple(sorted([a,b])),[]).append(i)
  for edge,owners in edge_map.items():
   if len(owners)!=2:continue
   i,j=owners;ids=list(set(polygons[i]+polygons[j]));
   try:hull=ConvexHull(xy[ids])
   except QhullError:continue
   def area(poly):
    v=xy[poly];return abs((v[:,0]*np.roll(v[:,1],-1)-v[:,1]*np.roll(v[:,0],-1)).sum())/2
   if abs(hull.volume-area(polygons[i])-area(polygons[j]))>1e-5:continue
   # Preserve collinear vertices in polygon perimeter for subsequent exact-edge merges.
   edges=[]
   for poly in [polygons[i],polygons[j]]:
    edges.extend([tuple(sorted([a,b])) for a,b in zip(poly,poly[1:]+poly[:1]) if tuple(sorted([a,b]))!=edge])
   graph={}
   for a,b in edges:graph.setdefault(a,[]).append(b);graph.setdefault(b,[]).append(a)
   if not all(len(v)==2 for v in graph.values()):continue
   start=min(graph);seq=[start];prev=None;cur=start
   while True:
    nxt=next(v for v in graph[cur] if v!=prev)
    if nxt==start:break
    seq.append(nxt);prev,cur=cur,nxt
   polygons[i]=seq;polygons.pop(j);merged=True;break
 print('parts',len(polygons),[len(poly)for poly in polygons],flush=True)
 # Actual exterior uses compact top/bottom hulls and exact source profile perimeter walls.
 preview=[];leaf=[]
 for poly in polygons:
  hu=ConvexHull(xy[poly]);ids=np.array(poly)[hu.vertices];v=q[ids];a=v.copy();b=v.copy();a[:,1]=lo;b[:,1]=hi
  pts=np.concatenate([a,b]);hull=ConvexHull(pts);leaf.append(pts[hull.simplices])
  for k in range(1,len(a)-1):preview.extend([a[[0,k,k+1]],b[[0,k+1,k]]])
 edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1);edges,c=np.unique(edges,axis=0,return_counts=True)
 for u,v in edges[c==1]:
  a=q[u].copy();b=q[v].copy();a[1]=lo;b[1]=lo;aa=a.copy();bb=b.copy();aa[1]=hi;bb[1]=hi;preview.extend([np.array([a,b,bb]),np.array([a,bb,aa])])
 target=np.array(preview);fv=dist(p,target);rv=dist(np.unique(target.reshape(-1,3),axis=0),g);fs=dist(area_samples(g,50000,31),target);rs=dist(area_samples(target,50000,37),g)
 print('preview',len(target),'leaf',sum(len(x)for x in leaf),'errors',fv.max(),rv.max(),fs.max(),rs.max(),flush=True)
 box=row['box'];c,f,half=map(np.array,[box['center_mm'],box['axes_columns'],box['half_extents_mm']]);f=f[:,np.argsort(half)[::-1]];render_pair(row,g,g,target,f,c,max(half)*1.2,'core-65-profile')
 np.savez_compressed(OUT/'core-65-profile.npz',world_triangles_mm=target,leaf_triangles_mm=np.concatenate(leaf),leaf_triangle_counts=np.array([len(x)for x in leaf]),source_triangle_indices=np.array(row['triangle_indices']))
 rec={**row,'kind':'exact-profile-convex-compound','native_leaf_count':len(leaf),'native_placed_leaves':len(leaf)*row['placements'],'preview_exterior_triangles':len(target),'preview_per_leaf_triangles':sum(len(x)for x in leaf),'hypothetical_placed_exterior_savings':(len(g)-len(target))*row['placements'],'hypothetical_placed_per_leaf_preview_savings':(len(g)-sum(len(x)for x in leaf))*row['placements'],'native_placed_triangle_mesh_triangles_replaced':len(g)*row['placements'],'source_all_vertex_max_mm':float(fv.max()),'reverse_all_vertex_max_mm':float(rv.max()),'source_area_max_mm':float(fs.max()),'reverse_area_max_mm':float(rs.max()),'minimum_extent_mm':hi-lo,'samples_each_direction':50000,'status':'research only; exact-coordinate shared-edge merging; convex-profile area test; verify manifold and attachments before adoption','preview_files':['core-65-profile-before.png','core-65-profile-diagnostic-after.png']}
 (OUT/'profile.json').write_text(json.dumps(rec,indent=2)+'\n')
if __name__=='__main__':run()
