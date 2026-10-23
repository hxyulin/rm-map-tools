import sys,json,hashlib
sys.dont_write_bytecode=True
from research import *
def cap_loops(g):
 p,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3);cr=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);normal=cr[np.argmax(np.linalg.norm(cr,axis=1))];normal/=np.linalg.norm(normal);seed=np.eye(3)[np.argmin(abs(normal))];x=np.cross(seed,normal);x/=np.linalg.norm(x);f=np.column_stack([x,np.cross(normal,x),normal]);local=p@f;axis=2;levels=[local[:,axis].min(),local[:,axis].max()];out=[]
 for level in levels:
  mask=np.max(abs(local[t,axis]-level),axis=1)<.01;tri=t[mask];e=np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1);e,c=np.unique(e,axis=0,return_counts=True);e=e[c==1];adj={}
  for a,b in e:adj.setdefault(int(a),[]).append(int(b));adj.setdefault(int(b),[]).append(int(a))
  if any(len(v)!=2 for v in adj.values()):out.append(dict(level=level,status='non-loop boundary',edges=len(e)));continue
  unseen=set(adj);loops=[]
  while unseen:
   start=min(unseen);seq=[start];prev=None;cur=start
   while True:
    nxt=next(v for v in adj[cur] if v!=prev)
    if nxt==start:break
    seq.append(nxt);prev,cur=cur,nxt
   unseen.difference_update(seq);q=p[seq];xy=local[seq,:2];area=abs(np.sum(xy[:,0]*np.roll(xy[:,1],-1)-xy[:,1]*np.roll(xy[:,0],-1)))/2
   _,_,lv=np.linalg.svd(q-q.mean(0),full_matrices=False);spans=np.ptp((q-q.mean(0))@lv.T,axis=0)
   loops.append(dict(vertex_count=len(q),projected_convex_fill_area_mm2=float(max(0,ConvexHull(xy).volume-area)),world_vertices_mm=q.tolist(),area_mm2=float(area),principal_spans_mm=spans.tolist(),world_center_mm=q.mean(0).tolist()))
  loops=sorted(loops,key=lambda x:-x['area_mm2']);out.append(dict(level=level,cap_triangles=int(mask.sum()),outer=loops[0] if loops else None,holes=loops[1:]))
 return out

def main():
 r=json.loads((OUT/'verified.json').read_text());screen=json.loads((OUT/'screen.json').read_text());doc,cs,nodes=load_nodes(Path(screen['source']))
 for row in r['records']:
  ni=row['node'];ids=row['selector']['triangle_indices'];g=nodes[ni][ids]
  if ni in [121,122,123]:row['cap_boundary_diagnostic']=cap_loops(g)
  z=np.load(OUT/f'rune-{ni}-hull-trial.npz');hh=ConvexHull(z['positions_mm']);fp=np.concatenate([g.reshape(-1,3),area_samples(g,80000,531)]);row['source_outside_hull_max_mm']=float(max(0,(fp@hh.equations[:,:3].T+hh.equations[:,3]).max()));row['source_inside_depth_sampled_max_mm']=row['forward_surface']['max_mm']
  if ni==123:row['interpretation']='Clipped-corner 3mm support plate; hull preserves convex outer profile but fills elongated narrow fastener slots. Conditional deliberate fastener-slot fill, not an opening-preserving proxy.'
  elif ni in [121,122]:row['interpretation']='Long 3mm support strip; replace only main exact island, retain all 176 triangles from four small attached islands. Hull retains outer strip profile and closes six narrow fastener slots, approximately 23–25mm long by 5mm wide. Conditional deliberate fastener-slot fill.'
  elif ni==192:row['interpretation']='Rejected: perimeter notches filled and source is effectively zero-thickness sheet (~0.000029mm PCA thickness), unsuitable as one volumetric native hull. No savings counted.'
  else:row['interpretation']='Rejected: structural outline notch, step or assembly opening filled; no savings counted.'
 shortlist=[x for x in r['records'] if x['node'] in [121,122,123]]
 total=dict(selected_nodes=[121,122,123],placements=1,source_selected_triangles=sum(x['source_triangles'] for x in shortlist),native_hull_leaves=3,retained_original_mesh_leaves=2,preview_mesh_leaves=5,retained_original_triangles=sum(x['retained_attached_island_triangles'] for x in shortlist),preview_hull_triangles=sum(x['hull_preview_triangles'] for x in shortlist),placed_native_triangles_removed=sum(x['placed_native_triangles_removed'] for x in shortlist),placed_preview_triangle_savings=sum(x['placed_preview_triangle_savings'] for x in shortlist),approved_or_installed_savings=0)
 result=dict(source_review=str(REF),pins=r['pins'],scope='Rune collision only; no installed/frozen/runtime/visual edits, dependencies, builds or commits.',coverage=dict(mesh_nodes=410,excluded_prior_nodes=[22,23,272,426],exact_island_inventory_nodes=len(screen['inventory']),screened_rows=len(screen['rows']),screened_distinct_nodes=len(set(x['node'] for x in screen['rows'])),fine_verified_nodes=[x['node'] for x in r['records']],screen_threshold='>=300 source triangles, >=40mm longest world axis span, convex envelope saves >=200 preview triangles; each exact connected island and whole source node if multiple islands; 1500 area samples per direction plus vertices'),candidates=shortlist,rejections=[x for x in r['records'] if x['node'] not in [121,122,123]],totals=total,limitations=['All three candidates intentionally fill narrow fastener holes or slots; none is an opening-preserving equivalent. Explicit collision-detail policy review required before adoption.','Fine measured maxima use every source/hull vertex, triangle centroid/midpoint, edge samples at <=1mm, plus deterministic 80000/120000 area samples. Finite sampling, not continuous Hausdorff/contact certification.','No native hull field importer was implemented; existing native hull runtime support does not make diagnostic mesh previews installed colliders. No FPS or timing inference.','No symmetry extrapolation: all source nodes independently matched; prior cylinder nodes 22/23/272/426 excluded. Rest-pose world frames must remain attached to original node ancestry.'])
 (OUT/'shortlist.json').write_text(json.dumps(result,indent=2)+'\n')
 (OUT/'verified.json').write_text(json.dumps(r,indent=2)+'\n')
 checks=[]
 for p,s in r['pins'].items():assert digest(Path(p))==s;checks.append(dict(path=p,sha256=s))
 ref=json.loads(REF.read_text())
 for p,s in ref.get('pins',{}).items():assert digest(Path(p))==s;checks.append(dict(path=p,sha256=s))
 for row in r['records']:
  g=nodes[row['node']];ids=np.array(row['selector']['triangle_indices']);lab,n=topology(g);assert np.array_equal(ids,np.flatnonzero(lab==0));assert digest(Path(row['source']))==row['source_sha256'];assert hashlib.sha256(ids.astype('<i8').tobytes()).hexdigest()==row['selector']['triangle_indices_sha256'];assert hashlib.sha256(g[ids].astype('<f8').tobytes()).hexdigest()==row['selector']['selected_triangle_coordinates_float64_mm_sha256']
 for im in r['renders']:assert digest(ROOT/im['path'])==im['sha256']
 verification=dict(all_pins_unchanged=True,input_pins=checks,selectors_recomputed_and_exact=True,render_hashes_passed=True,script_sha256={str(p.relative_to(ROOT)):digest(p) for p in Path(__file__).parent.glob('*.py')},artifact_sha256={str(p.relative_to(ROOT)):digest(p) for p in OUT.glob('*.json') if p.name!='validation.json'})
 (OUT/'validation.json').write_text(json.dumps(verification,indent=2)+'\n')
 print(json.dumps(total,indent=2))
 for x in shortlist:print(x['node'],json.dumps(x['cap_boundary_diagnostic']))
if __name__=='__main__':main()
