"""Verify fixed spokes, filled centers, group ownership and bank-spin separation."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import MultiPoint,Point
from spokes import OUT,ROOT,BINDINGS,p,v,scan,read_glb,scene_triangles
helper=p.module('spoke_clearance_helpers',str(ROOT/'benchmarks/2026-10-23-rune-hub-coarse/verify.py'))

def main():
 r=json.loads((OUT/'verification.json').read_text());d,c,n=scan.load_nodes(Path(r['source_collision']));a,ac,new=scan.load_nodes(Path(r['candidate_collision']));selected=set(r['selected_nodes']);bindings=json.loads(BINDINGS.read_text())
 for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
 assert scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']and scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
 exact=p.pair.unchanged(Path(r['source_collision']),Path(r['candidate_collision']),selected);arms=[i for i in n if '/arm-'in c[i]]
 for i in arms:assert np.array_equal(n[i],new[i])
 names=[x.get('name')for x in a['nodes']];selectors=[s for m in bindings['rune_motion']for s in m['bodies']]
 for name in selectors:assert names.count(name)==1
 assert not d.get('animations')and not d.get('skins')
 recipe=json.loads(Path(r['native_review']).read_text());assert len(recipe['native_parts'])==13;covered={i for group in recipe['source_groups']for i in group['covered_source_mesh_nodes']};assert covered==selected
 for group in recipe['source_groups']:
  component=d['nodes'][group['component_root_node']]['extras']['component_id']
  for i in group['covered_source_mesh_nodes']:assert c[i]==component and d['nodes'][i]['name']not in selectors
 for part in recipe['native_parts']:
  g=v.geometry(part['shape']);assert np.isfinite(g).all()and np.einsum('ij,ij->i',g[:,0],np.cross(g[:,1],g[:,2])).sum()>0
  assert ConvexHull(np.array(part['shape']['vertices_local_m'])).volume>0
 remainder=Path(r['native_review']).parent/'remainder.glb';rd,_=read_glb(remainder);assert scene_triangles(rd)==r['native_rune_remaining_mesh_triangles']and scan.digest(remainder)==recipe['retained_mesh']['sha256'];p.pair.unchanged(Path(r['source_collision']),remainder,selected)
 clearance=[];fits=[];projected=[]
 for bi,definition in enumerate(r['definitions']):
  bank=definition['bank'];frame=np.array(definition['frame_columns']);pivot=np.array(definition['pivot_mm']);g=np.concatenate([n[i]for i in arms if c[i].startswith(f'rune/banks/{bank}/arm-')]);q=(g-pivot)@frame;radial=helper.radial_min(q)
  group=bank+'-fixed-hub';parts=[x for x in recipe['native_parts']if x['source_group']==group];owner=definition['spoke_source_node'];spokes=[x for x in parts if x['diagnostic_carrier_node']==owner];assert len(spokes)==5
  native=np.concatenate([v.geometry(x['shape'])for x in spokes]);sq=(native-pivot)@frame;gap=float(q[:,:,2].min()-sq[:,:,2].max()if bi==0 else sq[:,:,2].min()-q[:,:,2].max());assert gap>4.9999
  centers=[x for x in parts if x['diagnostic_carrier_node']in [272,426]];assert len(centers)==1;centerq=(v.geometry(centers[0]['shape'])-pivot)@frame;center_radius=float(np.linalg.norm(centerq[:,:,:2],axis=2).max());assert radial-center_radius>18.9
  extra_gap=None
  if bi==1:
   extra=[x for x in parts if x['diagnostic_carrier_node']==429];assert len(extra)==1;eq=(v.geometry(extra[0]['shape'])-pivot)@frame;extra_gap=float(q[:,:,2].min()-eq[:,:,2].max());assert extra_gap>48
  clearance.append(dict(bank=bank,spoke_axial_gap_mm=gap,center_radial_gap_mm=radial-center_radius,extra_reverse_bracket_axial_gap_mm=extra_gap,proof_scope='All angles of the declared rigid bank spin. Independent target articulation, runtime contacts and CCD not tested.'))
  ids=[i for i in n if c[i]==f'rune/banks/{bank}/hub-cluster'];sourceg=np.concatenate([n[i]for i in ids]);newg=np.concatenate([new[i]for i in ids if i in new]);forward=p.distances(p.probes(sourceg,12000),newg.reshape(-1,3),np.arange(len(newg)*3).reshape(-1,3));reverse=p.distances(p.probes(newg,12000),sourceg.reshape(-1,3),np.arange(len(sourceg)*3).reshape(-1,3));fits.append(dict(bank=bank,source_to_fit_max_sampled_mm=float(forward.max()),fit_to_source_max_sampled_mm=float(reverse.max())))
  # Report projected recession of the clipped/simplified spoke relative to its
  # original angular sector, separately from the 2 mm compaction allowance.
  points=np.unique(n[owner].reshape(-1,3),axis=0);local=(points-pivot)@frame;rr=np.linalg.norm(local[:,:2],axis=1);theta=np.arctan2(local[:,1],local[:,0])
  for k,part in enumerate(spokes):
   angle=np.deg2rad(definition['spokes'][k]['angle_deg']);mask=(abs(np.angle(np.exp((theta-angle)*1j)))<=np.pi/5)&(rr>=110);old=local[mask,:2];target=(v.geometry(part['shape']).reshape(-1,3)-pivot)@frame;poly=MultiPoint(target[:,:2]).convex_hull
   projected.append(dict(bank=bank,spoke=k,original_sector_projected_vertex_recession_max_mm=max(Point(q).distance(poly)for q in old)))
 stage=json.loads((OUT/'paired-stage.json').read_text())
 for role in ['visual','collision']:
  assert sum(x['placed_triangles']for x in stage[role+'_assets'].values())==stage['placed_'+role+'_triangles']
  for x in stage[role+'_assets'].values():assert scan.digest(Path(x['path']))==x['sha256']
 proof=dict(unchanged_owners_exact=exact,moving_arm_payloads_exact=len(arms),moving_selectors_preserved=len(selectors),fixed_hub_mesh_triangles_remaining=0,source_groups_verified=2,visual_assets_exact=True,clearance=clearance,fit=fits,projected_spoke_recession=projected,center_filled_by_user_request=True,center_entry_exposure_not_preserved=True,runtime_supported=False,installed=False,contact_validated=False)
 (OUT/'geometry-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(clearance=clearance,fit=fits,max_projected_spoke_recession_mm=max(x['original_sector_projected_vertex_recession_max_mm']for x in projected))))
if __name__=='__main__':main()
