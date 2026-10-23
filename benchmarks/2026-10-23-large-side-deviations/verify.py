"""Verify source pins, selectors, exact seam positions and local topology."""
import sys,json
sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
from investigate import OUT,ROOT,REF,sha,load_nodes,topology

def edge_counts(g):
 p,t,lab,n=topology(g);edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);e,c=np.unique(edges,axis=0,return_counts=True)
 return dict(triangles=len(g),vertices=len(p),islands=n,boundary_edges=int(np.sum(c==1)),nonmanifold_edges=int(np.sum(c>2)),degenerate_triangles=int(np.sum(np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1)<1e-9)))

def all_edges(g):
 p,t,_,_=topology(g);edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1)
 return {tuple(sorted((tuple(p[a]),tuple(p[b]))))for a,b in edges}

def seam(g):
 p,t,_,_=topology(g);edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);e,c=np.unique(edges,axis=0,return_counts=True)
 return {tuple(sorted((tuple(p[a]),tuple(p[b]))))for a,b in e[c==1]}

def run():
 r=json.loads((OUT/'measurements.json').read_text());s=json.loads((OUT/'shortlist.json').read_text());assert sha(REF)==r['reference_sha256']
 for path,digest in r['pins'].items():assert sha(Path(path))==digest
 cache={};records=[]
 for ni in sorted({x['node']for x in s['panels']}):
  node=next(x for x in r['nodes']if x['asset']=='base'and x['node']==ni)
  if node['source']not in cache:cache[node['source']]=load_nodes(Path(node['source']))[2]
  g=cache[node['source']][ni];remove=[];add=[]
  for x in s['panels']:
   if x['node']!=ni:continue
   assert x['disjoint_from_prior_selected_patches'];ids=np.array(x['source_triangle_indices']);assert ids.min()>=0 and ids.max()<len(g)
   z=np.load(OUT/f'base-{ni}-panel-{x["patch_index"]}-trial.npz');target=z['positions_mm'][z['triangles']];assert seam(g[ids])==seam(target)
   shared_edges=all_edges(g[ids]) & all_edges(np.delete(g,ids,axis=0));assert shared_edges <= all_edges(target)
   source_n=np.cross(g[ids,1]-g[ids,0],g[ids,2]-g[ids,0]).sum(0);target_n=np.cross(target[:,1]-target[:,0],target[:,2]-target[:,0]).sum(0);assert source_n@target_n>0
   remove.extend(ids.tolist());add.append(target)
  assert len(remove)==len(set(remove));trial=np.concatenate([np.delete(g,remove,axis=0),*add]);before=edge_counts(g);after=edge_counts(trial)
  assert before['boundary_edges']==after['boundary_edges'];assert before['nonmanifold_edges']==after['nonmanifold_edges'];assert before['islands']==after['islands'];assert after['degenerate_triangles']==0
  records.append(dict(asset='base',node=ni,source_unit_id=node['node_extras']['source_unit_id'],source=before,assembled_in_memory_trial=after,seam_positions_and_segments_exact=True,orientation_consistent=True))
 result=dict(pins_unchanged=True,selector_and_seam_checks_passed=True,owners=records,script_sha256={str(p.relative_to(ROOT)):sha(p)for p in sorted(Path(__file__).parent.glob('*.py'))},limitations='Assembly only in memory under the same source node. Topology counts and identical seams do not prove no intersection, no contact changes, continuous geometric bounds or pose clearance. No export/install/build/commit.')
 (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['owners'],indent=2))
if __name__=='__main__':run()
