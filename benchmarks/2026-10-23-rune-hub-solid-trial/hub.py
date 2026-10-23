"""Per-owner Rune hub convex envelopes, all arms and visuals retained."""
import copy,importlib.util,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-core-head-primitives'))
import build as v
p=v.p;scan=v.scan
from gltf_scene import read_glb,write_glb,scene_nodes
from simplify_package import compact,scene_triangles
OUT=ROOT/'out/rmuc2027-rune-hub-solid-trial'
BASE=ROOT/'out/rmuc2027-core-head-rod-base-plate/rod-base-plate/verification.json'
STAGE=ROOT/'out/rmuc2027-core-head-rod-base-plate/rod-base-plate/paired-stage.json'
BINDINGS=ROOT.parent/'rm-simulator/field-2027/rmuc2027-bindings.json'
SELECTED=[272,273,274,426,427,428]
OPEN_CENTERS=False

def open_sections(points,center,axis,apothem=58.):
 from scipy.optimize import linprog
 from scipy.spatial import HalfspaceIntersection
 a,u,w=p.basis(axis);frame=np.column_stack([u,w,a]);q=(points-center)@frame;h=ConvexHull(q);shapes=[]
 for k in range(5):
  angle=k*2*np.pi/5;radial=np.array([np.cos(angle),np.sin(angle),0]);tangent=np.array([-np.sin(angle),np.cos(angle),0]);slope=np.tan(np.pi/5)
  half=np.vstack([h.equations,np.r_[-radial,apothem],np.r_[tangent-radial*slope,0],np.r_[-tangent-radial*slope,0]])
  lengths=np.linalg.norm(half[:,:3],axis=1);half=half/lengths[:,None]
  solution=linprog([0,0,0,-1],A_ub=np.column_stack([half[:,:3],np.ones(len(half))]),b_ub=-half[:,3],bounds=[(None,None)]*3+[(0,None)],method='highs')
  if not solution.success or solution.x[3]<1e-5:continue
  vertices=HalfspaceIntersection(half,solution.x[:3]).intersections@frame.T+center
  selected,_,_=v.compact_hull(vertices,tolerance=.25);selected=selected[ConvexHull(selected).vertices];origin=selected.mean(0)
  shapes.append(dict(kind='convex_hull',vertices_local_m=((selected-origin)/1000).tolist(),pose=dict(translation_m=(origin/1000).tolist(),rotation_xyzw=[0,0,0,1])))
 return shapes

def replace(source,target,replacements):
 d,blob=read_glb(source);a=copy.deepcopy(d);binary=bytearray(blob);world={i:w for i,w,parent in scene_nodes(d)}
 for i,g in replacements.items():
  old=d['meshes'][d['nodes'][i]['mesh']];inv=np.linalg.inv(world[i]);local=(g*.001)@inv[:3,:3].T+inv[:3,3]
  new=copy.deepcopy(old);new['primitives']=[p.pair.primitive(a,binary,local*1000,old['primitives'][0])]
  a['nodes'][i]['mesh']=len(a['meshes']);a['meshes'].append(new)
 write_glb(target,a,compact(a,binary));p.pair.unchanged(source,target,set(replacements))

def main():
 OUT.mkdir(exist_ok=True);stage=json.loads(STAGE.read_text());source=Path(stage['collision_assets']['rune']['path']);assert scan.digest(source)==stage['collision_assets']['rune']['sha256']
 d,c,n=scan.load_nodes(source);bindings=json.loads(BINDINGS.read_text());moving={name for row in bindings['rune_motion']for name in row['bodies']};parents={i:parent for i,w,parent in scene_nodes(d)}
 shapes=[];replacements={};measurements=[]
 for i in SELECTED:
  assert c[i].endswith('/hub-cluster')and d['nodes'][i]['name']not in moving
  pts=np.unique(n[i].reshape(-1,3),axis=0);outer=pts[ConvexHull(pts).vertices];selected,geo,recession=v.compact_hull(outer,tolerance=.5)
  h=ConvexHull(selected);selected=selected[h.vertices];center=selected.mean(0)
  shape=dict(kind='convex_hull',vertices_local_m=((selected-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1]))
  owner_shapes=[shape]
  if OPEN_CENTERS and i in [273,427]:
   disk=272 if i==273 else 426;diskpoints=n[disk].reshape(-1,3);diskcenter=(diskpoints.min(0)+diskpoints.max(0))/2
   owner_shapes=open_sections(selected,diskcenter,np.array([.93558540845,-.35310047224,0]))
  g=np.concatenate([v.geometry(s)for s in owner_shapes]);replacements[i]=g;anc=[];j=i
  while j is not None:anc.append(j);j=parents[j]
  for index,s in enumerate(owner_shapes):shapes.append(dict(id=f'rune-hub-{i}-{index}',source_node_index=i,source_node_name=d['nodes'][i]['name'],ancestor_nodes_root_first=anc[::-1],component_id=c[i],shape=s))
  forward=p.distances(p.probes(n[i],12000),g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3));reverse=p.distances(p.probes(g,20000),n[i].reshape(-1,3),np.arange(len(n[i])*3).reshape(-1,3))
  measurements.append(dict(node=i,name=d['nodes'][i]['name'],component=c[i],source_triangles=len(n[i]),preview_triangles=len(g),native_hulls=len(owner_shapes),hull_vertices=sum(len(s['vertices_local_m'])for s in owner_shapes),outer_vertex_recession_max_mm=recession,
    source_surface_to_hull_surface_max_mm=float(forward.max()),hull_surface_to_source_max_mm=float(reverse.max()),fills_holes_recesses_and_owner_concavities=True))
  print(i,len(n[i]),'to hull',len(selected),'vertices; reverse',float(reverse.max()),flush=True)
 target=OUT/'rune-collision.glb';replace(source,target,replacements);exact=p.pair.unchanged(source,target,set(SELECTED));td,tb=read_glb(target);count=scene_triangles(td)
 remainder=copy.deepcopy(d);_,blob=read_glb(source)
 for i in SELECTED:del remainder['nodes'][i]['mesh']
 folder=OUT/'native-review';folder.mkdir(exist_ok=True);write_glb(folder/'remainder.glb',remainder,compact(remainder,blob));rem,_=read_glb(folder/'remainder.glb');p.pair.unchanged(source,folder/'remainder.glb',set(SELECTED))
 recipe=dict(schema='rm-map-tools.native-primitive-review-1',units='m',coordinate_frame='source_glb_active_scene',quaternion_order='xyzw',source=dict(file=str(source),sha256=scan.digest(source)),
  retained_mesh=dict(file='remainder.glb',sha256=scan.digest(folder/'remainder.glb'),triangles=scene_triangles(rem)),replaced_node_indices=SELECTED,native_parts=shapes,runtime_supported=False,installed=False)
 (folder/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
 old=json.loads(BASE.read_text());newstage=copy.deepcopy(stage);newstage['collision_assets']['rune']=dict(path=str(target),sha256=scan.digest(target),triangles=count,placements=1,placed_triangles=count)
 newstage['placed_collision_triangles']=sum(row['placed_triangles']for row in newstage['collision_assets'].values());newstage.update(variant='rune-hub-solid-trial',installed=False,contact_validated=False)
 (OUT/'paired-stage.json').write_text(json.dumps(newstage,indent=2)+'\n')
 report=dict(source_collision=str(source),source_sha256=scan.digest(source),candidate_collision=str(target),candidate_sha256=scan.digest(target),selected_nodes=SELECTED,measurements=measurements,
 unchanged_other_owners_exact=exact,source_rune_triangles=scene_triangles(d),diagnostic_rune_triangles=count,native_rune_remaining_mesh_triangles=scene_triangles(rem),new_native_hulls=len(shapes),central_disk_clearance=dict(enabled=OPEN_CENTERS,apothem_mm=58 if OPEN_CENTERS else None,sections_per_frame=5 if OPEN_CENTERS else 1),
 native_mesh_triangles_saved=sum(len(n[i])for i in SELECTED),field_native_mesh_triangles=old['field_native_mesh_triangles']-sum(len(n[i])for i in SELECTED),
 field_native_shape_counts={**old['field_native_shape_counts'],'convex_hull':old['field_native_shape_counts']['convex_hull']+len(shapes)},field_preview_triangles=newstage['placed_collision_triangles'],
 native_review=str(folder/'recipe.json'),unchanged_visual=stage['visual_assets']['rune']['path'],unchanged_visual_sha256=stage['visual_assets']['rune']['sha256'],
 input_pins={str(path):scan.digest(path)for path in [BASE,STAGE,BINDINGS,source,Path(stage['visual_assets']['rune']['path'])]},runtime_supported=False,installed=False,contact_validated=False)
 (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print('Saved',report['native_mesh_triangles_saved'],'native mesh triangles; preview',count,flush=True)
def build_screened(open_centers=False):
 global OUT,SELECTED,OPEN_CENTERS
 root=OUT;original=SELECTED
 try:
  OUT=root/('open-centers'if open_centers else'clearance-screened');SELECTED=[272,273,426,427];OPEN_CENTERS=open_centers;main()
  path=OUT/'verification.json';r=json.loads(path.read_text());r['input_pins'][str(root/'sweep-screen.json')]=scan.digest(root/'sweep-screen.json');r['rejected_whole_bracket_nodes']=[274,428];r['sweep_screen']=str(root/'sweep-screen.json');path.write_text(json.dumps(r,indent=2)+'\n')
 finally:OUT=root;SELECTED=original;OPEN_CENTERS=False

if __name__=='__main__':
 if '--open-centers'in sys.argv:build_screened(True)
 elif '--screened'in sys.argv:build_screened()
 else:main()
