import sys,json,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
from research import *
from PIL import Image,ImageDraw
import collision_review_render as raster

def metrics(probes,g):
 v=distances(probes,g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3));i=int(np.argmax(v));return dict(max_mm=float(v[i]),samples=len(v),worst_point_mm=probes[i].tolist(),over_1mm=int(np.sum(v>1)),over_3mm=int(np.sum(v>3)))
def probes(g,count,seed):
 p=g.reshape(-1,3);mid=(g+np.roll(g,1,axis=1))/2
 edges=[]
 # All triangle edges at <=1 mm pitch, exact vertices, centroids and random area samples.
 for j in range(3):
  a=g[:,j];b=g[:,(j+1)%3];n=np.ceil(np.linalg.norm(b-a,axis=1)).astype(int)
  for aa,bb,nn in zip(a,b,n):
   if nn>1:edges.append(aa+(bb-aa)*np.linspace(0,1,nn+1)[:,None])
 return np.concatenate([p,g.mean(1),mid.reshape(-1,3),area_samples(g,count,seed),*edges])
def data(g,col):
 g=g*.001@np.array([[1,0,0],[0,0,-1],[0,1,0]])
 return(g,np.tile(col,(len(g),1)),np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),None,np.zeros((1,1,3),np.uint8))
def main():
 screen=json.loads((OUT/'screen.json').read_text());path=Path(screen['source']);doc,comps,nodes=load_nodes(path);scene={i:(w,p)for i,w,p in scene_nodes(doc)};records=[];renders=[];tiles=[]
 work=OUT/'raster-work';work.mkdir(exist_ok=True);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
 for ni in [121,122,123,192,154,62]:
  g=nodes[ni];labels,n=topology(g);ids=np.flatnonzero(labels==0);h=g[ids];remain=g[labels!=0];p=np.unique(h.reshape(-1,3),axis=0);hull=ConvexHull(p);target=p[hull.simplices]
  fp=probes(h,80000,531);rp=probes(target,120000,532);fm=metrics(fp,target);rm=metrics(rp,h)
  fits=fit_boxes(h);box=fits[0] if fits else None
  if box:
   c,f,half=map(np.asarray,[box['center_mm'],box['axes_columns'],box['half_extents_mm']]);bg=box_points(c,f,half)[FACES];box['fine_forward']=metrics(fp,bg);box['fine_reverse']=metrics(probes(bg,40000,533),h)
  ancestry=[];a=ni
  while a is not None:
   ancestry.append(dict(node=a,name=doc['nodes'][a].get('name'),extras=doc['nodes'][a].get('extras',{})));a=scene[a][1]
  center=p.mean(0);_,_,vt=np.linalg.svd(p-center,full_matrices=False);frame=vt.T;spans=np.ptp((p-center)@frame,axis=0);score=max(fm['max_mm'],rm['max_mm'])
  # Width and thickness accompany total span; plate thickness is not a permissive tolerance.
  row=dict(asset='rune',source=str(path),source_sha256=screen['source_sha256'],node=ni,name=doc['nodes'][ni].get('name'),component=comps[ni],node_extras=doc['nodes'][ni].get('extras',{}),ancestry_node_to_root=ancestry,source_world_matrix_metres=scene[ni][0].tolist(),selector=dict(kind='exact-coordinate-connected-island',island_label=0,triangle_indices=ids.tolist(),triangle_indices_sha256=hashlib.sha256(ids.astype('<i8').tobytes()).hexdigest(),selected_triangle_coordinates_float64_mm_sha256=hashlib.sha256(h.astype('<f8').tobytes()).hexdigest(),order='scan.load_nodes concatenated source primitive triangle order, zero based'),source_triangles=len(h),owner_source_triangles=len(g),retained_attached_island_triangles=len(remain),owner_exact_islands=n,placements=screen['placements'],hull_vertices=len(hull.vertices),hull_preview_triangles=len(target),native_hull_leaves=1,native_replacement_surface_triangles=0,owner_retained_mesh_leaves=1 if len(remain) else 0,owner_preview_triangles=len(target)+len(remain),preview_triangle_savings=len(h)-len(target),placed_native_triangles_removed=len(h)*screen['placements'],placed_preview_triangle_savings=(len(h)-len(target))*screen['placements'],forward_surface=fm,reverse_surface=rm,symmetric_sampled_max_mm=score,local_feature_metrics=dict(pca_frame_columns=frame.tolist(),pca_spans_mm=spans.tolist(),error_over_longest_span=score/max(spans),error_over_middle_span=score/sorted(spans)[1],error_over_thinnest_span=score/min(spans)),box=box,status='conditional-small-detail-fill-review' if ni in [121,122,123] else 'reject-hull-fills-structural-gap',bounds_mm=[p.min(0).tolist(),p.max(0).tolist()])
  # Exact native vertices in owner-local coordinates, same transforms/ancestry.
  hp=p[hull.vertices];inv=np.linalg.inv(scene[ni][0]);local=(np.c_[hp*.001,np.ones(len(hp))]@inv.T)[:,:3]
  row['native_hull_world_vertices_mm']=hp.tolist();row['native_hull_owner_local_vertices_metres']=local.tolist()
  np.savez(OUT/f'rune-{ni}-hull-trial.npz',positions_mm=p,triangles=hull.simplices,source_triangle_indices=ids,retained_triangles_mm=remain)
  records.append(row);print(ni,'fine',fm['max_mm'],rm['max_mm'],'box',box['fine_forward']['max_mm'],box['fine_reverse']['max_mm'],flush=True)
  before=data(g,[.56,.66,.75]);after=data(np.concatenate([target,remain]),[.9,.58,.22]);focus=np.concatenate([before[0],after[0]])
  cr=np.cross(h[:,1]-h[:,0],h[:,2]-h[:,0]);face=cr[np.argmax(np.linalg.norm(cr,axis=1))];face/=np.linalg.norm(face);fd=face@np.array([[1,0,0],[0,0,-1],[0,1,0]]);fd=fd+np.array([.001,.001,.001]);
  for view,direction in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1)),('face',fd.tolist())]:
   pair=[]
   for stage,d in [('before',before),('diagnostic-after',after)]:
    im=Image.fromarray(raster.raster(d,focus,direction,helper,work));fname=OUT/f'rune-{ni}-{view}-{stage}.webp';im.save(fname,lossless=True);renders.append(dict(node=ni,view=view,stage=stage,path=str(fname.relative_to(ROOT)),sha256=digest(fname),matched_camera=direction,frame='source active scene mm converted to review Y-up; identical union bounds'));pair.append(im.resize((450,450)))
   if view=='oblique':
    tile=Image.new('RGB',(920,490),'white');draw=ImageDraw.Draw(tile);draw.text((8,8),f'Rune {ni}: before / diagnostic hull; max {score:.3f} mm',fill='black');tile.paste(pair[0],(0,35));tile.paste(pair[1],(465,35));tiles.append(tile)
  if ni in [121,122,123]:
   # Whole Rune contextual pair, red selected owner and subdued surrounding mesh.
   context=np.concatenate([v for k,v in nodes.items() if k!=ni]);cb=data(context,[.52,.55,.57]);old=data(g,[.95,.3,.15]);new=data(np.concatenate([target,remain]),[.95,.6,.15]);cf=np.concatenate([cb[0],old[0],new[0]])
   def join(x,y):return tuple(np.concatenate([x[i],y[i]]) if i in [0,1,2,3] else x[i] for i in range(6))
   for stage,d in [('before',join(cb,old)),('diagnostic-after',join(cb,new))]:
    im=Image.fromarray(raster.raster(d,cf,(1,.65,1),helper,work));fname=OUT/f'rune-{ni}-context-{stage}.webp';im.save(fname,lossless=True);renders.append(dict(node=ni,view='whole-Rune-context',stage=stage,path=str(fname.relative_to(ROOT)),sha256=digest(fname)))
 for p,s in screen['pins'].items():assert digest(Path(p))==s
 sheet=Image.new('RGB',(1840,490*((len(tiles)+1)//2)),(235,235,235))
 for i,tile in enumerate(tiles):sheet.paste(tile,((i%2)*920,(i//2)*490))
 sheet.save(OUT/'matched-contact-sheet.jpg',quality=92)
 (OUT/'verified.json').write_text(json.dumps(dict(pins=screen['pins'],records=records,renders=renders,source_pins_unchanged=True,method='All original vertices, centroids, midpoints, triangle edges at <=1mm pitch plus 80000 source /120000 hull uniform area samples. VTK exact nearest triangles at finite probes. No percentiles used for acceptance; not continuous bounds.',native_semantics='One convex leaf attached to same source rigid node, plus original untouched remainder mesh if present. Preview facets are diagnostic only; current field import supports cylinders only.'),indent=2)+'\n')
if __name__=='__main__':main()
