import research as r
from research import *
from panel_trial import render as old_render
import panel_trial
import vtk
panel_trial.OUT=OUT

def render_pair(row,g,h,target,frame,center,scale,prefix):
 rest=np.delete(g,row['triangle_indices'],axis=0)
 bounds=tuple(v for pair in zip(g.min((0,1)),g.max((0,1))) for v in pair)
 cam=vtk.vtkCamera();direction=frame@np.array([.35,.25,1.]);direction/=np.linalg.norm(direction);cam.SetPosition(*(center+direction*5000));cam.SetFocalPoint(*center);cam.SetViewUp(*frame[:,1]);cam.ParallelProjectionOn();cam.SetParallelScale(scale)
 for stage,geom in [('before',h),('diagnostic-after',target)]:old_render(rest,geom,cam,bounds,f'{prefix}-{stage}.png')

def measure():
 screen=json.loads((OUT/'screen.json').read_text());cache={};rows=[]
 targets={'tech-core':[6,31,53,54,55,56,61,65], 'outpost':[26,28,30]}
 for row in screen['rows']:
  if row['node'] not in targets.get(row['asset'],[]):continue
  if row['source'] not in cache:cache[row['source']]=load_nodes(Path(row['source']))[2]
  g=cache[row['source']][row['node']];h=g[row['triangle_indices']];p=np.unique(h.reshape(-1,3),axis=0)
  trials=[]
  hull=ConvexHull(p)
  # Both exact hull and oriented enclosing box, no trimmed geometry.
  box=row['box'];c,f,half=map(np.array,[box['center_mm'],box['axes_columns'],box['half_extents_mm']])
  for kind,target in [('convex-hull',p[hull.simplices]),('box',box_points(c,f,half)[FACES])]:
   fv=dist(p,target);rv=dist(np.unique(target.reshape(-1,3),axis=0),h)
   fs=dist(area_samples(h,30000,31),target);rs=dist(area_samples(target,30000,37),h)
   # Include every source/target triangle centroid and edge midpoint for thin features.
   def feature_samples(q):return np.concatenate([q.mean(1),(q[:,0]+q[:,1])/2,(q[:,1]+q[:,2])/2,(q[:,2]+q[:,0])/2])
   ff=dist(feature_samples(h),target);rf=dist(feature_samples(target),h)
   mm=max(fv.max(),rv.max(),fs.max(),rs.max(),ff.max(),rf.max())
   trial=dict(kind=kind,preview_triangles=len(target),native_leaf_count=1,source_all_vertex_max_mm=float(fv.max()),reverse_all_vertex_max_mm=float(rv.max()),source_area_max_mm=float(fs.max()),reverse_area_max_mm=float(rs.max()),source_feature_max_mm=float(ff.max()),reverse_feature_max_mm=float(rf.max()),sampled_bidirectional_max_mm=float(mm),area_samples_each_direction=30000,minimum_oriented_extent_mm=float(2*half.min()),max_over_min_extent=float(mm/(2*half.min())),hypothetical_placed_preview_savings=int((len(h)-len(target))*row['placements']),native_placed_triangle_mesh_triangles_replaced=int(len(h)*row['placements']),native_placed_leaves=row['placements'])
   trials.append(trial)
   np.savez_compressed(OUT/f'{row["asset"]}-{row["node"]}-{kind}.npz',world_triangles_mm=target,source_triangle_indices=np.array(row['triangle_indices']),source_world_matrix_metres=np.array(row['source_world_matrix_metres']))
   print(row['asset'],row['node'],kind,len(h),len(target),'max',mm,'thin',2*half.min(),flush=True)
   if kind=='box' or row['asset']=='outpost':
    # Frame reordered to put thinnest dimension toward camera.
    axes=np.argsort(half)[::-1];rfm=f[:,axes];render_pair(row,g,h,target,rfm,c,max(half)*1.2,f'{row["asset"]}-{row["node"]}-{kind}')
  rows.append({**row,'trials':trials})
 (OUT/'measurements.json').write_text(json.dumps(dict(pins=screen['pins'],rows=rows),indent=2)+'\n')
 for p,s in screen['pins'].items():assert sha(Path(p))==s
if __name__=='__main__':measure()
