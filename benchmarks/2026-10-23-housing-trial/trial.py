# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-bound finite sheet/profile trials; never modifies runtime inputs."""
import sys,json,hashlib,copy,argparse
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
import shapely
from shapely.geometry import Polygon
from gltf_scene import read_glb,write_glb,accessor,scene_nodes
from simplify_package import append_accessor,compact,scene_triangles,protected
from cad_collision_profiles import prism_mesh,mesh_metrics
from cad_dense_lod import surface_samples
from mesh_quality import distances
import importlib.util
spec=importlib.util.spec_from_file_location('refine',ROOT/'benchmarks/2026-10-23-runtime-opportunities/refine.py');refine=importlib.util.module_from_spec(spec);spec.loader.exec_module(refine)
OUT=ROOT/'out/rmuc2027-housing-trial';BASE=ROOT/'out/rmuc2027-runtime-opportunities/refined';PKG=ROOT.parent/'rm-simulator/field-2027'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(d,b,p):
 q=accessor(d,b,p['attributes']['POSITION']).astype(float)*1000;t=accessor(d,b,p['indices']).reshape(-1,3);return q[t]
def appearance(d,p):return json.dumps({k:v for k,v in d['materials'][p['material']].items() if k not in ('name','extras')},sort_keys=True)
def profile(g,n,tol=.5,hole=6):
 n=n/np.linalg.norm(n);x=np.cross(np.eye(3)[np.argmin(abs(n))],n);x/=np.linalg.norm(x);y=np.cross(n,x);basis=np.array([x,y]);o=g.reshape(-1,3).mean(0);uv=(g-o)@basis.T;depth=(g-o)@n;lo,hi=depth.min(),depth.max()
 if hi-lo<.05:raise ValueError('not finite')
 # Project source faces, not a convex hull: broad through-openings survive.
 u=uv[:,1]-uv[:,0];v=uv[:,2]-uv[:,0];a=np.abs(u[:,0]*v[:,1]-u[:,1]*v[:,0]);uv=uv[a>1e-6]
 domain=shapely.union_all(shapely.polygons(uv),grid_size=.001)
 polys=list(domain.geoms) if domain.geom_type=='MultiPolygon' else [domain]
 if not polys or domain.is_empty:raise ValueError('empty source projection')
 if len(polys)!=1:raise ValueError('disconnected source projection')
 poly=polys[0];removed=[];retained=[]
 for ring in poly.interiors:
  h=Polygon(ring);width=float(np.ptp(np.array(ring.coords),axis=0).max())
  if width<hole:removed.append({'width_bound_mm':width,'area_mm2':h.area})
  else:retained.append(ring)
 original_poly=Polygon(poly.exterior,retained);poly=original_poly.simplify(tol,preserve_topology=True)
 outer_error=float(shapely.hausdorff_distance(original_poly.exterior,poly.exterior,densify=.25))
 if outer_error>tol+.002:raise ValueError('silhouette exceeds allowance')
 if poly.is_empty or poly.area<.01:raise ValueError('empty simplified profile')
 loops=[{'outer':True,'points_mm':o+np.array(poly.exterior.coords)[:-1]@basis+hi*n}]
 loops +=[{'outer':False,'points_mm':o+np.array(r.coords)[:-1]@basis+hi*n} for r in poly.interiors]
 p,t,top=prism_mesh(loops,n,float(hi-lo))
 if np.any(np.linalg.norm(np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]]),axis=1)<1e-9):raise ValueError('degenerate profile caps')
 return p,t,{'depth_mm':float(hi-lo),'normal':n.tolist(),'outline_tolerance_mm':tol,'projected_outer_boundary_max_mm':outer_error,'closed_holes':removed,'retained_holes':len(poly.interiors),'source_projected_components':1,'topology':top,'strict_hole_width_mm':hole}
def requests(sd,sb,cd,cb,groups,asset,role):
 worlds={i:w for i,w,_ in scene_nodes(sd)};inherited={};blocked={}
 for i,w,parent in scene_nodes(sd):
  inherited[i]=sd['nodes'][i].get('extras',{}).get('component_id') or inherited.get(parent,'')
  blocked[i]=blocked.get(parent,False) or protected(sd['nodes'][i].get('extras',{}).get('rm',{}))
 grouped=set();rows=[]
 for group in groups:
  if len(group['source_nodes'])!=1:continue
  i=group['source_nodes'][0];scope=group['scope_node']
  if i!=scope:continue
  children=[j for j in cd['nodes'][scope].get('children',[]) if cd['nodes'][j].get('name','').startswith('derived-planar-panels-')]
  matches=[j for j in children if cd['meshes'][cd['nodes'][j]['mesh']]['primitives'][0]['material']==group['material']]
  if len(matches)!=1:continue
  j=matches[0];prim=cd['meshes'][cd['nodes'][j]['mesh']]['primitives'][0];app=appearance(cd,prim)
  src=[(pi,p) for pi,p in enumerate(sd['meshes'][sd['nodes'][i]['mesh']]['primitives']) if appearance(sd,p)==app and refine.structural(sd['materials'][p['material']],p)]
  if not src:continue
  grouped.update((i,pi) for pi,p in src)
  rows.append((i,j,0,np.concatenate([load(sd,sb,p) for pi,p in src]),group['after_triangles'],[pi for pi,p in src]))
 # Non-reconstructed baseline primitives retain direct source correspondence.
 for i,w,parent in scene_nodes(sd):
  node=sd['nodes'][i]
  if 'mesh' not in node or 'mesh' not in cd['nodes'][i]:continue
  sp=sd['meshes'][node['mesh']]['primitives'];cp=cd['meshes'][cd['nodes'][i]['mesh']]['primitives']
  if len(sp)!=len(cp):continue
  for pi,(s,c) in enumerate(zip(sp,cp)):
   if (i,pi) in grouped:continue
   if not refine.structural(sd['materials'][s['material']],s):
    allowed={'outpost':{10,14,25},'base':{8,10,11,12,13,48}}
    if role!='collision' or i not in allowed.get(asset,set()):continue
   rows.append((i,i,pi,load(sd,sb,s),len(accessor(cd,cb,c['indices']))//3,[pi]))
 for i,j,pi,g,cost,src in rows:
  if cost<80 or blocked[i] or (asset=='base' and sd['nodes'][i].get('name')=='source_body_4268930'):continue
  if role=='visual' and asset!='arena-static' and any(not refine.structural(sd['materials'][p['material']],p) for p in sd['meshes'][sd['nodes'][i]['mesh']]['primitives']):continue
  if asset=='arena-static' and not inherited[i].startswith('dart-station'):continue
  # Explicitly exclude chromatic/optical neighbors and all moving Outpost rotor modules.
  identity=str(sd['nodes'][i].get('extras',{})).lower()
  if asset=='outpost' and ('rotor' in identity or 'module-' in identity):continue
  yield {'source_node':i,'target_node':j,'target_primitive':pi,'source_primitives':src,'name':sd['nodes'][i].get('name'),'component':inherited[i],'baseline_triangles':cost},g

def run():
 global OUT
 parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=['near','coarse'],default='near');args=parser.parse_args();allowance=1.2 if args.variant=='near' else 10;hole=6 if args.variant=='near' else 17;OUT=OUT/args.variant
 OUT.mkdir(parents=True,exist_ok=True);ledger={'policy':'Finite source-projected connected-piece prisms plus finite Dart planar aperture fills. Preserve all projected holes at or above the recorded variant width. Deliberately close smaller apertures; profile silhouette allowance 0.5mm, Dart panel boundary allowance 0.05mm. Local sampled deviation limited by the recorded variant allowance. No optical/chromatic/UV or moving rotor replacement. Inspection only; no runtime speedup measured.','assets':{},'trials':[],'variant':args.variant,'maximum_local_sampled_allowance_mm':allowance,'strict_hole_width_mm':hole}
 refined=json.loads((BASE.parent/'refined.json').read_text())
 for relative in ['manifest.json','equipment/manifest.json']:
  manifest=json.loads((PKG/relative).read_text())
  for asset,a in manifest['assets'].items():
   if asset not in ['arena-static','outpost','base']:continue
   for role in ['visual','collision']:
    key=asset+'/'+role;src=PKG/Path(relative).parent/a[role];base=BASE/(role+'-1mm')/a[role];target=OUT/(role+'-1mm')/a[role]
    sd,sb=read_glb(src);cd,cb=read_glb(base);
    worlds={i:w for i,w,_ in scene_nodes(sd)};protected_geometry=[]
    if role=='visual':
     for ni,w,pa in scene_nodes(sd):
      node=sd['nodes'][ni]
      if 'mesh' not in node:continue
      for prim in sd['meshes'][node['mesh']]['primitives']:
       if not refine.structural(sd['materials'][prim['material']],prim):
        gg=load(sd,sb,prim);protected_geometry.append(gg@w[:3,:3].T+w[:3,3]*1000)
    protected_g=np.concatenate(protected_geometry) if protected_geometry else np.empty((0,3,3))
    out=copy.deepcopy(cd);binary=bytearray(cb);selected=[];cache={}
    for row,g in requests(sd,sb,cd,cb,refined['assets'][key]['groups'],asset,role):
     from connected import rebuild
     cp=cd['meshes'][cd['nodes'][row['target_node']]['mesh']]['primitives'][row['target_primitive']];cg=load(cd,cb,cp)
     replacement,parts=rebuild(g,cg,lambda g,n:profile(g,n,hole=hole),allowance=allowance)
     if args.variant=='coarse' and not parts and asset=='arena-static':
      from apertures import fill
      replacement,parts=fill(g,cg)
     ledger['trials'].append({'asset':key,**row,'changed_connected_pieces':parts})
     if not parts:continue
     if len(protected_g):
      oldkeys={a.tobytes() for a in cg};newkeys={a.tobytes() for a in replacement};delta=[a for a in cg if a.tobytes() not in newkeys]+[a for a in replacement if a.tobytes() not in oldkeys]
      if delta:
       delta=np.array(delta);w=worlds[row['source_node']];world_delta=delta@w[:3,:3].T+w[:3,3]*1000;near=distances(surface_samples(world_delta.reshape(-1,3),np.arange(world_delta.size//3).reshape(-1,3)).reshape(-1,3),protected_g.reshape(-1,3),np.arange(protected_g.size//3).reshape(-1,3));clearance=float(near.min())
       if clearance<2:
        ledger['trials'][-1]['rejected_protected_neighbor_sampled_clearance_mm']=clearance
        continue
       for part in parts:part['protected_neighbor_sampled_clearance_mm']=clearance
     twice_area=np.linalg.norm(np.cross(replacement[:,1]-replacement[:,0],replacement[:,2]-replacement[:,0]),axis=1);degenerate_count=int((twice_area<=1e-9).sum());oldkeys={a.tobytes() for a in cg};inherited_degenerates=sum(a.tobytes() in oldkeys for a in replacement[twice_area<=1e-9]);assert inherited_degenerates==degenerate_count,'new cap has degenerate triangles';replacement=replacement[twice_area>1e-9]
     q=replacement.reshape(-1,3);t=np.arange(len(q)).reshape(-1,3);trial={**row,'output_triangles':len(t),'dropped_degenerate_output_triangles':degenerate_count,'degenerate_faces_all_inherited_from_baseline':True,'pieces':parts,'forward_max_mm':max(p['forward_max_mm'] for p in parts),'reverse_max_mm':max(p['reverse_max_mm'] for p in parts),'intentional_losses':'Flatten local bevel/recess relief and fill apertures below the recorded variant threshold; explicit per-piece sampled allowance; not global 1mm.'};best=q,t,trial
     q,t,trial=best;node=row['target_node'];pi=row['target_primitive'];old=out['meshes'][out['nodes'][node]['mesh']]
     # Never edit a mesh shared by another owner.
     new=copy.deepcopy(old);geo=q[t]/1000;norm=np.cross(geo[:,1]-geo[:,0],geo[:,2]-geo[:,0]);norm/=np.maximum(np.linalg.norm(norm,axis=1,keepdims=True),1e-30)
     corner_norm=np.repeat(norm[:,None],3,axis=1)
     if 'NORMAL' in cp['attributes']:
      old_n=accessor(cd,cb,cp['attributes']['NORMAL'])[accessor(cd,cb,cp['indices']).reshape(-1,3)];lookup={a.tobytes():b for a,b in zip(cg,old_n)}
      for k,triangle in enumerate(replacement):
       if triangle.tobytes() in lookup:corner_norm[k]=lookup[triangle.tobytes()]
     positions=np.ascontiguousarray(geo.reshape(-1,3),dtype='<f4');normals=np.ascontiguousarray(corner_norm.reshape(-1,3),dtype='<f4');attr,inv=np.unique(np.column_stack([positions,normals]),axis=0,return_inverse=True);positions=np.ascontiguousarray(attr[:,:3]);normals=np.ascontiguousarray(attr[:,3:]);ix=np.ascontiguousarray(inv,dtype=np.uint32)
     assert np.isfinite(positions).all() and np.isfinite(normals).all()
     prim=copy.deepcopy(new['primitives'][pi]);prim['attributes']={'POSITION':append_accessor(out,binary,positions,'VEC3',5126),'NORMAL':append_accessor(out,binary,normals,'VEC3',5126)};prim['indices']=append_accessor(out,binary,ix,'SCALAR',5125);prim.setdefault('extras',{}).update(derived_geometry=True,inspection_only=True,native_identity_claim=False,housing_profile_trial=True);new['primitives'][pi]=prim
     meshkey=(positions.tobytes(),normals.tobytes(),ix.tobytes(),prim['material']) if len(new['primitives'])==1 else None
     reused=cache.get(meshkey) if meshkey else None
     if reused is None:
      reused=len(out['meshes']);out['meshes'].append(new)
      if meshkey:cache[meshkey]=reused
     out['nodes'][node]['mesh']=reused;selected.append(trial)
     print(key,row['name'],row['baseline_triangles'],'->',len(t),trial['forward_max_mm'],trial['reverse_max_mm'],flush=True)
    if not selected:continue
    out['asset'].setdefault('extras',{}).update(inspection_only=True,collision_approved=False,housing_trial='source-projected-finite-prisms-v1')
    payload=compact(out,binary);target.parent.mkdir(parents=True,exist_ok=True);write_glb(target,out,payload);actual,blob=read_glb(target)
    for mesh in actual['meshes']:
     for p in mesh['primitives']:
      for semantic in ['POSITION','NORMAL']:
       if semantic in p['attributes']:assert np.isfinite(accessor(actual,blob,p['attributes'][semantic])).all()
    assert actual['materials']==cd['materials'];assert len(actual['nodes'])==len(cd['nodes'])
    for (i,w,p),(j,v,pa) in zip(scene_nodes(cd),scene_nodes(actual)):assert i==j and p==pa and np.array_equal(w,v)
    def stored(d):return sum(p and d['accessors'][p['indices']]['count']//3 for mi in {d['nodes'][i]['mesh'] for i,_,_ in scene_nodes(d) if 'mesh' in d['nodes'][i]} for p in d['meshes'][mi]['primitives'])
    placements=max(1,len(a['placements_in_source_arena_frame']));before=scene_triangles(cd);after=scene_triangles(actual)
    assert after<before
    ledger['assets'][key]={'input':str(src.resolve()),'input_sha256':digest(src),'baseline':str(base.resolve()),'baseline_sha256':digest(base),'output':str(target.resolve()),'output_sha256':digest(target),'placements':placements,'baseline_stored_triangles':stored(cd),'candidate_stored_triangles':stored(actual),'baseline_scene_triangles':before,'candidate_scene_triangles':after,'baseline_placed_triangles':before*placements,'candidate_placed_triangles':after*placements,'changed_pieces':selected,'reopen_verified':True,'node_indices_and_frames_preserved':True}
 ledger['producer_sha256']={str(p.resolve()):digest(p) for p in Path(__file__).parent.glob('*.py')}
 ledger['stage_inputs']=[]
 for relative in ['manifest.json','equipment/manifest.json']:
  for asset,a in json.loads((PKG/relative).read_text())['assets'].items():
   for role in ['visual','collision']:
    key=asset+'/'+role;base=BASE/(role+'-1mm')/a[role];source=PKG/Path(relative).parent/a[role];chosen=ledger['assets'].get(key,{}).get('output',str(base.resolve()))
    ledger['stage_inputs'].append({'asset':asset,'role':role,'baseline':str(base.resolve()),'candidate':chosen,'input':str(source.resolve()),'input_sha256':digest(source),'baseline_sha256':digest(base),'candidate_sha256':digest(Path(chosen)),'placements':a['placements_in_source_arena_frame']})
 (OUT/'ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
 print('RESULT',[(k,v['baseline_placed_triangles']-v['candidate_placed_triangles']) for k,v in ledger['assets'].items()])
if __name__=='__main__':run()
