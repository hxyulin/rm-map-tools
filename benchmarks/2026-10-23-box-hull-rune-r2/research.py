import sys,json,hashlib,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-box-primitive-candidates'))
from scan import *
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
OUT=ROOT/'out/rmuc2027-box-hull-rune-r2';REF=ROOT/'out/rmuc2027-installed-reference-review/review.json'
def topology(g):
 p,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3);e=np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]);n,lab=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(p),len(p))),directed=False);return lab[t[:,0]],n

def run():
 ref=json.loads(REF.read_text());pins={str(REF):digest(REF)}
 for role in ref['roles'].values():
  for info in role['assets'].values():
   path=Path(info['path']);assert digest(path)==info['sha256'];pins[str(path)]=digest(path)
 info=ref['roles']['collision']['assets']['rune'];path=Path(info['path']);doc,comps,nodes=load_nodes(path);scene={i:(w,p)for i,w,p in scene_nodes(doc)}
 rows=[];inventory=[]
 for ni,g in nodes.items():
  if ni in [22,23,272,426]:continue
  labels,n=topology(g);inventory.append(dict(node=ni,triangles=len(g),exact_islands=n))
  sets=[(lab,np.flatnonzero(labels==lab))for lab in range(n)]
  # A whole-node hull also exposes rejected merged concave members.
  if n>1:sets.append(('whole',np.arange(len(g))))
  for lab,ids in sets:
   h=g[ids];p=np.unique(h.reshape(-1,3),axis=0);span=np.ptp(p,axis=0)
   if len(h)<300 or span.max()<40:continue
   try: hull=ConvexHull(p)
   except QhullError:continue
   if len(hull.simplices)>=len(h)-200:continue
   target=p[hull.simplices];probes=np.concatenate([p[hull.vertices],area_samples(target,1500,321)])
   reverse=distances(probes,h.reshape(-1,3),np.arange(len(h)*3).reshape(-1,3))
   # Halfspace distance gives lower bound to forward surface distance for interiors;
   # exact VTK distance is used in fine verification, this screen uses it too.
   fprobes=np.concatenate([p,area_samples(h,1500,322)])
   forward=distances(fprobes,target.reshape(-1,3),np.arange(len(target)*3).reshape(-1,3))
   row=dict(node=ni,island=lab,source_triangles=len(h),owner_triangles=len(g),owner_islands=n,hull_facets=len(target),hull_vertices=len(hull.vertices),span_mm=span.tolist(),screen_forward_max_mm=float(forward.max()),screen_reverse_max_mm=float(reverse.max()),component=comps[ni],name=doc['nodes'][ni].get('name'))
   rows.append(row);print(ni,lab,len(h),'hull',len(target),'errors',round(forward.max(),3),round(reverse.max(),3),flush=True)
 for p,s in pins.items():assert digest(Path(p))==s
 (OUT/'screen.json').write_text(json.dumps(dict(pins=pins,source=str(path),source_sha256=info['sha256'],placements=info['placements'],mesh_nodes=len(nodes),excluded_nodes=[22,23,272,426],inventory=inventory,rows=rows),indent=2)+'\n')
if __name__=='__main__':run()
