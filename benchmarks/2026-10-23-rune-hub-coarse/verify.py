"""Verify coarse silhouettes, analytical bank-spin separation and disk exposure."""
import json
from pathlib import Path
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
from scipy.spatial import ConvexHull
from coarse import OUT,BINDINGS,p,scan,geometry,read_glb,scene_triangles

def locator(g,owners):
 pts=vtk.vtkPoints();pts.SetData(numpy_to_vtk(g.reshape(-1,3).astype(float),deep=True));cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(g),3),np.arange(len(g)*3).reshape(-1,3)]).astype(np.int64).ravel(),deep=True));poly=vtk.vtkPolyData();poly.SetPoints(pts);poly.SetPolys(cells);loc=vtk.vtkStaticCellLocator();loc.SetDataSet(poly);loc.BuildLocator();return loc,owners

def radial_min(q):
 a=q[:,:,:2];mins=[]
 for i in range(3):
  start=a[:,i];edge=a[:,(i+1)%3]-start;t=np.clip(-np.einsum('ij,ij->i',start,edge)/np.maximum((edge*edge).sum(1),1e-30),0,1);mins.append(np.linalg.norm(start+t[:,None]*edge,axis=1))
 cross=[a[:,i,0]*a[:,(i+1)%3,1]-a[:,i,1]*a[:,(i+1)%3,0]for i in range(3)];cross=np.column_stack(cross);area=abs(cross.sum(1));inside=((cross>=-1e-10).all(1)|(cross<=1e-10).all(1))&(area>1e-8)
 result=np.min(mins,axis=0);result[inside]=0;return float(result.min())

def exposures(n,new,c,bank,disk):
 ids=sorted(i for i in n if c[i]==f'rune/banks/{bank}/hub-cluster');locs={}
 for name,geos in [('source',n),('candidate',new)]:
  chosen=[i for i in ids if i in geos];g=np.concatenate([geos[i]for i in chosen]);owners=np.concatenate([np.full(len(geos[i]),i)for i in chosen]);locs[name]=locator(g,owners)
 pts=scan.area_samples(n[disk],1000,seed=274);_,_,vt=np.linalg.svd(n[disk].reshape(-1,3)-n[disk].reshape(-1,3).mean(0),full_matrices=False);normal=vt[-1];rows=[]
 for sign in [-1,1]:
  lengths={};hitowners={}
  for name,(loc,owners)in locs.items():
   result=[];who=[]
   for pt in pts:
    t=vtk.reference(0.);cell=vtk.reference(0);sub=vtk.reference(0);point=[0.,0.,0.];pc=[0.,0.,0.];hit=loc.IntersectWithLine(pt+sign*normal*600,pt-sign*normal*50,1e-7,t,point,pc,sub,cell);result.append(float(t)*650 if hit else np.nan);who.append(int(owners[int(cell)])if hit else-1)
   lengths[name]=np.array(result);hitowners[name]=np.array(who)
  mask=hitowners['source']==disk;delta=lengths['source']-lengths['candidate'];lost=mask&(hitowners['candidate']!=disk)
  # The requested coarse cylinder fills rim detail; allow at most 5 mm
  # hit-distance change, while preserving the exact first-hit disk owner.
  assert not lost.any()and not (delta[mask]>5).any()
  rows.append(dict(bank=bank,disk=disk,sign=sign,rays=len(pts),disk_first_owner_preserved=True,max_earlier_mm=float(np.nanmax(delta))))
 return rows

def main():
 bindings=json.loads(BINDINGS.read_text())
 for variant in ['simple-frame','coarse-hub']:
  out=OUT/variant;r=json.loads((out/'verification.json').read_text());d,c,n=scan.load_nodes(Path(r['source_collision']));a,ac,new=scan.load_nodes(Path(r['candidate_collision']));selected=set(r['selected_nodes'])
  for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
  assert scan.digest(Path(r['candidate_collision']))==r['candidate_sha256']and scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
  exact=p.pair.unchanged(Path(r['source_collision']),Path(r['candidate_collision']),selected);arms=[i for i in n if '/arm-'in c[i]]
  for i in arms:assert np.array_equal(n[i],new[i])
  moving=[s for motion in bindings['rune_motion']for s in motion['bodies']];names=[x.get('name')for x in a['nodes']]
  for name in moving:assert names.count(name)==1
  recipe=json.loads(Path(r['native_review']).read_text());remainder=Path(r['native_review']).parent/'remainder.glb';rd,_=read_glb(remainder);assert scene_triangles(rd)==r['native_rune_remaining_mesh_triangles'];p.pair.unchanged(Path(r['source_collision']),remainder,selected)
  assert scan.digest(remainder)==recipe['retained_mesh']['sha256']
  for part in recipe['native_parts']:
   shape=part['shape'];assert part['component_id'].endswith('/hub-cluster')
   g=geometry(shape);assert np.isfinite(g).all()and np.einsum('ij,ij->i',g[:,0],np.cross(g[:,1],g[:,2])).sum()>0
   if shape['kind']=='cylinder':assert shape['radius_m']>0 and shape['length_m']>0
   elif shape['kind']=='box':assert min(shape['half_extents_m'])>0
   else:assert ConvexHull(np.array(shape['vertices_local_m'])).volume>0
  clearance=[];exposure=[];fits=[]
  for idx,definition in enumerate(r['definitions']):
   bank=definition['bank'];disk=272 if idx==0 else 426;frame=np.array(definition['frame_columns']);pivot=np.array(definition['pivot_mm']);arm_geo=np.concatenate([n[i]for i in arms if c[i].startswith(f'rune/banks/{bank}/arm-')]);q=(arm_geo-pivot)@frame;radial=radial_min(q)
   if variant=='coarse-hub':
    assert radial>140.;rear=definition['rear_ring_axial_mm'];gap=q[:,:,2].min()-rear[1]if idx==0 else rear[0]-q[:,:,2].max();assert gap>=4.99999
    clearance.append(dict(bank=bank,rear_ring_axial_gap_mm=float(gap),neck_radial_gap_mm=radial-140,arm_triangle_radial_min_mm=radial,proof_scope='All angles of the installed rigid bank spin, using triangle-projection radial minima and vertex axial extrema. Independent target articulation and runtime/CCD not tested.'))
   else:
    z=definition['square_frame_axial_mm'];gap=q[:,:,2].min()-z[1]if idx==0 else z[0]-q[:,:,2].max();assert gap>100;clearance.append(dict(bank=bank,frame_axial_gap_mm=float(gap)))
   exposure.extend(exposures(n,new,c,bank,disk))
   ids=[i for i in n if c[i]==f'rune/banks/{bank}/hub-cluster'];source_geo=np.concatenate([n[i]for i in ids]);new_geo=np.concatenate([new[i]for i in ids if i in new]);forward=p.distances(p.probes(source_geo,10000),new_geo.reshape(-1,3),np.arange(len(new_geo)*3).reshape(-1,3));reverse=p.distances(p.probes(new_geo,10000),source_geo.reshape(-1,3),np.arange(len(source_geo)*3).reshape(-1,3));fits.append(dict(bank=bank,source_to_fit_max_sampled_mm=float(forward.max()),fit_to_source_max_sampled_mm=float(reverse.max())))
  stage=json.loads((out/'paired-stage.json').read_text())
  for role in ['visual','collision']:
   assert sum(x['placed_triangles']for x in stage[role+'_assets'].values())==stage['placed_'+role+'_triangles']
   for x in stage[role+'_assets'].values():assert scan.digest(Path(x['path']))==x['sha256']
  proof=dict(variant=variant,unchanged_owners_exact=exact,moving_arm_meshes_exact=len(arms),moving_selectors_preserved=len(moving),visual_assets_exact=True,clearance=clearance,disk_exposure=exposure,fit=fits,runtime_supported=False,installed=False,contact_validated=False)
  (out/'geometry-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(variant,json.dumps(dict(clearance=clearance,fit=fits)),flush=True)
if __name__=='__main__':main()
