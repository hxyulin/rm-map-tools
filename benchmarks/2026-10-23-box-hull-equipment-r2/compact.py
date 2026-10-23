from measure import *

def greedy_hull(p,tolerance):
 # All selected hull vertices are source vertices. Add exact worst omitted source vertex.
 selected=set()
 for d in np.concatenate([np.eye(3),-np.eye(3)]):selected.add(int(np.argmax(p@d)))
 for i in range(200):
  ids=np.array(sorted(selected));hu=ConvexHull(p[ids]);target=p[ids][hu.simplices];d=dist(p,target);j=int(np.argmax(d))
  if d[j]<=tolerance:return target,ids
  selected.add(j)
 raise RuntimeError('budget')

def run():
 screen=json.loads((OUT/'screen.json').read_text());rows=[]
 for row in screen['rows']:
  if row['asset']!='tech-core' or row['node'] not in [53,54,55,56]:continue
  g=load_nodes(Path(row['source']))[2][row['node']];h=g[row['triangle_indices']];p=np.unique(h.reshape(-1,3),axis=0)
  target,ids=greedy_hull(p,.5)
  fv=dist(p,target);rv=dist(np.unique(target.reshape(-1,3),axis=0),h);fs=dist(area_samples(h,50000,31),target);rs=dist(area_samples(target,50000,37),h)
  mm=max(fv.max(),rv.max(),fs.max(),rs.max());box=row['box'];c,f,half=map(np.array,[box['center_mm'],box['axes_columns'],box['half_extents_mm']]);axes=np.argsort(half)[::-1];f=f[:,axes]
  prefix=f'core-{row["node"]}-compact';render_pair(row,g,h,target,f,c,max(half)*1.2,prefix)
  rec={**row,'kind':'compact-inscribed-convex-hull','selected_unique_vertex_indices':ids.tolist(),'hull_vertices':len(ids),'preview_triangles':len(target),'native_leaf_count':1,'native_placed_leaves':row['placements'],'native_placed_triangle_mesh_triangles_replaced':len(h)*row['placements'],'hypothetical_placed_preview_savings':(len(h)-len(target))*row['placements'],'source_all_vertex_max_mm':float(fv.max()),'reverse_all_vertex_max_mm':float(rv.max()),'source_area_max_mm':float(fs.max()),'reverse_area_max_mm':float(rs.max()),'sampled_bidirectional_max_mm':float(mm),'samples_each_direction':50000,'minimum_extent_mm':float(2*half.min()),'max_over_thickness':float(mm/(2*half.min())),'status':'research-shortlist; outline recession <=0.5mm at all source vertices; finite surface checks; no contact approval','preview_files':[prefix+'-before.png',prefix+'-diagnostic-after.png']}
  np.savez_compressed(OUT/(prefix+'.npz'),world_triangles_mm=target,source_triangle_indices=np.array(row['triangle_indices']),source_world_matrix_metres=np.array(row['source_world_matrix_metres']))
  rows.append(rec);print('compact',row['node'],len(h),len(target),'verts',len(ids),'max',mm,flush=True)
 (OUT/'compact.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':run()
