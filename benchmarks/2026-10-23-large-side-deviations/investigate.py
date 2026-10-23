"""Pinned installed collision investigation. Only own output directory is written.
Triangle selectors index scan.load_nodes concatenated primitive triangle order.
"""
import sys,json,hashlib
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import ConvexHull,QhullError
ROOT=Path(__file__).resolve().parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-box-primitive-candidates'))
from scan import load_nodes,fit_boxes,area_samples,box_points,FACES,scene_nodes
from mesh_quality import distances
OUT=ROOT/'out/rmuc2027-large-side-deviations'
REF=ROOT/'out/rmuc2027-installed-reference-review/review.json'
TARGETS={'base':[8,13,10,11,12], 'outpost':[10,14,25], 'arena-static':[354]}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def topology(g):
 p,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3)
 e=np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]);n,lab=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(p),len(p))),directed=False)
 return p,t,lab[t[:,0]],n

def stats(g):
 cr=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);a=np.linalg.norm(cr,axis=1)/2
 return a,cr/np.maximum(2*a[:,None],1e-30)

def selector(ids):
 ids=np.asarray(ids,dtype='<i8');return dict(triangle_indices=ids.tolist(),triangle_indices_sha256=hashlib.sha256(ids.tobytes()).hexdigest())

def plane_fit(g):
 a,_=stats(g);center=np.sum(g.mean(1)*a[:,None],axis=0)/a.sum()
 # Exact uniform triangle surface second moment, not vertex-count PCA.
 x=g-center;s=x.sum(1)
 cov=np.einsum('i,ijk,ijl->kl',a,x,x)+np.einsum('i,ij,ik->jk',a,s,s)
 _,v=np.linalg.eigh(cov);normal=v[:,0];frame=v[:,[2,1,0]]
 local=x@frame;d=local[:,:,2]
 rms=np.sqrt(np.sum(a*(np.sum(d*d,axis=1)+np.sum(d,axis=1)**2)/12)/a.sum())
 samples=area_samples(g,12000,713);dev=abs((samples-center)@normal)
 return dict(center_mm=center.tolist(),normal=normal.tolist(),axes_columns=frame.tolist(),spans_mm=np.ptp(local.reshape(-1,3),axis=0).tolist(),area_mm2=float(a.sum()),rms_mm=float(rms),area_mean_abs_mm=float(dev.mean()),area_p95_mm=float(np.quantile(dev,.95)),area_p99_mm=float(np.quantile(dev,.99)),area_fraction_over_1mm=float(np.mean(dev>1)),all_vertex_max_mm=float(abs(d).max()))

def boundary(g,fit):
 p,t,_,_=topology(g);edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);e,c=np.unique(edges,axis=0,return_counts=True);b=e[c==1]
 degree=np.bincount(b.ravel(),minlength=len(p));ids=np.unique(b)
 result=dict(edges=len(b),vertices=len(ids),nonmanifold_edges=int(np.sum(c>2)),closed_loop_boundary=bool(len(b) and np.all(degree[ids]==2)))
 if result['closed_loop_boundary']:
  graph={int(i):[] for i in ids}
  for u,v in b:graph[int(u)].append(int(v));graph[int(v)].append(int(u))
  unseen=set(graph);loops=[]
  while unseen:
   start=min(unseen);seq=[start];prev=None;cur=start
   while True:
    nxt=next(q for q in graph[cur] if q!=prev)
    if nxt==start:break
    seq.append(nxt);prev,cur=cur,nxt
   unseen.difference_update(seq);loops.append(seq)
  f=np.asarray(fit['axes_columns']);xy=p@f[:,:2];areas=[]
  for loop in loops:
   q=xy[loop];areas.append(float(abs((q[:,0]*np.roll(q[:,1],-1)-q[:,1]*np.roll(q[:,0],-1)).sum())/2))
  result.update(loop_count=len(loops),loop_vertices=[len(x) for x in loops],projected_loop_areas_mm2=areas)
  # No invented boundary simplification: exact projected boundary vertex budget.
  result['exact_boundary_planar_triangle_budget']=len(b)+2*(len(loops)-1)-2
 return result

def patches(g):
 a,n=stats(g);orient=n.copy();sign=np.sign(orient[np.arange(len(n)),np.argmax(abs(n),axis=1)]);orient*=sign[:,None]
 key,inv=np.unique(np.round(orient,2),axis=0,return_inverse=True);weights=np.bincount(inv,weights=a)
 proposals=[];seen=[]
 for k in np.argsort(weights)[-12:][::-1]:
  normal=(orient[inv==k]*a[inv==k,None]).sum(0);normal/=np.linalg.norm(normal)
  dots=g@normal
  # Dominant face offsets generate fixed-width slabs; do not use vertex density.
  offsets=np.round(dots.mean(1)[inv==k],1);vals,ii=np.unique(offsets,return_inverse=True);ww=np.bincount(ii,weights=a[inv==k])
  for j in np.argsort(ww)[-6:][::-1]:
   level=vals[j]
   if any(abs(abs(normal@oldn)-1)<.001 and abs(level*(1 if normal@oldn>0 else -1)-oldl)<3 for oldn,oldl in seen):continue
   seen.append((normal,level))
   mask=np.max(abs(dots-level),axis=1)<=2.0
   ids=np.flatnonzero(mask)
   if len(ids)<8:continue
   _,_,lab,nc=topology(g[ids])
   for label in range(nc):
    select=ids[lab==label]
    if len(select)<8:continue
    h=g[select];fit=plane_fit(h)
    if min(fit['spans_mm'][:2])<50 or max(fit['spans_mm'][:2])<150 or fit['area_mm2']<5000:continue
    if any(len(np.intersect1d(select,q['triangle_indices']))>.8*min(len(select),q['source_triangles']) for q in proposals):continue
    proposals.append(dict(source_triangles=len(select),seed_slab_normal=normal.tolist(),seed_slab_level_mm=float(level),seed_slab_halfwidth_mm=2.,**selector(select),fit=fit,boundary=boundary(h,fit)))
 return sorted(proposals,key=lambda q:-q['source_triangles'])[:24]

def run():
 OUT.mkdir(exist_ok=True);ref=json.loads(REF.read_text());nodes=[];pins={}
 for asset,indices in TARGETS.items():
  info=ref['roles']['collision']['assets'][asset];path=Path(info['path']);assert sha(path)==info['sha256'];pins[str(path)]=sha(path)
  doc,components,groups=load_nodes(path)
  scene={index:(world,parent)for index,world,parent in scene_nodes(doc)}
  for ni in indices:
   g=groups[ni];p,t,lab,n=topology(g);a,_=stats(g)
   ancestry=[];ancestor=ni
   while ancestor is not None:
    ancestry.append(dict(node=ancestor,name=doc['nodes'][ancestor].get('name'),extras=doc['nodes'][ancestor].get('extras',{})));ancestor=scene[ancestor][1]
   row=dict(source_world_matrix_metres=scene[ni][0].tolist(),ancestry_node_to_root=ancestry,asset=asset,node=ni,name=doc['nodes'][ni].get('name'),component=components[ni],source=str(path),sha256=sha(path),placements=info['placements'],source_triangles=len(g),exact_coordinate_island_count=n,source_bounds_mm=[p.min(0).tolist(),p.max(0).tolist()],node_extras=doc['nodes'][ni].get('extras',{}),islands=[],patches=[])
   for label in range(n):
    ids=np.flatnonzero(lab==label);h=g[ids];span=np.ptp(h.reshape(-1,3),axis=0)
    if len(ids)<40 or span.max()<100:continue
    fits=fit_boxes(h)
    ir=dict(island_label=label,source_triangles=len(ids),area_mm2=float(a[ids].sum()),bounds_mm=[h.min((0,1)).tolist(),h.max((0,1)).tolist()],**selector(ids))
    if fits:
     best=fits[0];ir['box']=best
     if best['score']<=8:
      c,f,half=map(np.asarray,[best['center_mm'],best['axes_columns'],best['half_extents_mm']]);pts=box_points(c,f,half);samples=np.concatenate([pts,area_samples(pts[FACES],4096,27)])
      reverse=distances(samples,h.reshape(-1,3),np.arange(len(h)*3).reshape(-1,3))
      ir['box'].update(reverse_sampled_max_mm=float(reverse.max()),reverse_samples=len(samples),hypothetical_box_triangles=12)
    row['islands'].append(ir)
   row['patches']=patches(g);nodes.append(row)
   print(asset,ni,'islands',n,'large',len(row['islands']),'patches',len(row['patches']),flush=True)
 for p,s in pins.items():assert sha(Path(p))==s
 result=dict(reference=str(REF),reference_sha256=sha(REF),pins=pins,units='millimetres, source active-scene coordinates after inherited transforms',targets=TARGETS,nodes=nodes,method=dict(islands='Exact identical transformed float coordinates, connected by triangle edges. Does not bridge near seams.',patches='Connected triangle subsets wholly inside ±2 mm slab about dominant area-weighted normal/offset. This is a bounded subset, not a whole-side error guarantee. All selection indices are zero-based in load_nodes concatenated primitive order.',plane='Uniform triangle area-weighted least squares plane. RMS analytic exact triangle integral; mean/p95/p99 from 12000 deterministic area-uniform samples; all-vertex maximum exact for selected triangles.',boxes='Parent fit_boxes reused unchanged. All island vertices checked source→box; reverse finite 4096 area samples plus 8 corners. Not continuous Hausdorff or collision validation.'),limitations=['No native asset modification or exported collision candidate.','Projected panels retain selected boundary loops; actual triangulation, non-overlap, watertight integration, hole clearance, opposing thickness and contacts remain unresolved.','Selectors preserve source node identity; replacement must remain under whole original rigid/motion owner and inherit metadata/transforms. No owner splitting or moving-member merging.','Protected Core face, Armor and Rune visuals untouched.','Scope costs are not savings; planar patch boundaries may already dominate minimal triangle count.'])
 (OUT/'measurements.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':run()
