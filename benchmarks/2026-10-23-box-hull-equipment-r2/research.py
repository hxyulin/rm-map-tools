"""Bounded exact-island collision research. Writes only its own output directory."""
import sys,json,hashlib,time
from pathlib import Path
sys.dont_write_bytecode=True
import numpy as np
from scipy.spatial import ConvexHull,QhullError
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-box-primitive-candidates'))
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-large-side-deviations'))
from scan import load_nodes,fit_boxes,area_samples,box_points,FACES,scene_nodes,box_grid
from investigate import topology,selector
from mesh_quality import distances
OUT=ROOT/'out/rmuc2027-box-hull-equipment-r2'
REF=ROOT/'out/rmuc2027-installed-reference-review/review.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dist(p,g):return distances(p,g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3))
def signature(g):return hashlib.sha256(np.asarray(g,dtype='<f8').tobytes()).hexdigest()
def inventory():
 ref=json.loads(REF.read_text());pins={str(REF):sha(REF)}
 # Pin all visual/collision references and installed paths, not only researched assets.
 for p,s in ref['pins'].items():assert sha(Path(p))==s;pins[p]=s
 for role in ref['roles'].values():
  for info in role['assets'].values():assert sha(Path(info['path']))==info['sha256'];pins[info['path']]=info['sha256']
 rows=[];counts={}
 for asset in ['tech-core','base','outpost']:
  info=ref['roles']['collision']['assets'][asset];path=Path(info['path']);doc,components,nodes=load_nodes(path);scene={i:(w,p) for i,w,p in scene_nodes(doc)};counts[asset]={'nodes':len(nodes),'islands':0,'dense_screened':0}
  for ni,g in nodes.items():
   if asset=='tech-core' and ni in [22,68]:continue
   p,t,labels,n=topology(g);counts[asset]['islands']+=n
   for label in range(n):
    ids=np.flatnonzero(labels==label);h=g[ids]
    if len(ids)<160 or np.ptp(h.reshape(-1,3),axis=0).max()<40:continue
    counts[asset]['dense_screened']+=1
    ancestry=[];a=ni
    while a is not None:
     ancestry.append(dict(node=a,name=doc['nodes'][a].get('name'),extras=doc['nodes'][a].get('extras',{})));a=scene[a][1]
    fits=fit_boxes(h);fits=[f for f in fits if f['mode']=='enclosing'];fit=min(fits,key=lambda f:f['score']) if fits else None
    try: hull=ConvexHull(np.unique(h.reshape(-1,3),axis=0));hg=hull.points[hull.simplices]
    except QhullError:continue
    # Coarse reverse hull gate; also source interior distances expose bores and cavities.
    rs=dist(np.concatenate([hull.points[hull.vertices],area_samples(hg,1500,9)]),h)
    fs=dist(np.unique(h.reshape(-1,3),axis=0),hg)
    row=dict(asset=asset,node=ni,name=doc['nodes'][ni].get('name'),component=components[ni],island=label,source=str(path),source_sha256=info['sha256'],placements=info['placements'],owner_triangles=len(g),source_triangles=len(h),source_world_matrix_metres=scene[ni][0].tolist(),ancestry_node_to_root=ancestry,world_triangle_f64_sha256=signature(h),bounds_mm=[h.min((0,1)).tolist(),h.max((0,1)).tolist()],**selector(ids),box=fit,hull=dict(preview_triangles=len(hg),vertices=len(hull.vertices),coarse_reverse_max_mm=float(rs.max()),all_vertex_forward_max_mm=float(fs.max())))
    rows.append(row)
    print(asset,ni,label,len(h),'hull',len(hg),'F/R',round(fs.max(),2),round(rs.max(),2),'box',round(fit['score'],2) if fit else None,flush=True)
 for p,s in pins.items():assert sha(Path(p))==s
 (OUT/'screen.json').write_text(json.dumps(dict(pins=pins,counts=counts,rows=rows),indent=2)+'\n')
if __name__=='__main__':inventory()
