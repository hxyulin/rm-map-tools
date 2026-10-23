"""Verify admitted owners, complete arm preservation and stage integration."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from hub import ROOT,OUT as ROOT_OUT,scan,p,read_glb,scene_triangles,BINDINGS
OUT=ROOT_OUT/'open-centers'
def main():
 r=json.loads((OUT/'verification.json').read_text());source=Path(r['source_collision']);target=Path(r['candidate_collision']);d,c,n=scan.load_nodes(source);a,_,new=scan.load_nodes(target)
 assert scan.digest(source)==r['source_sha256']and scan.digest(target)==r['candidate_sha256']
 for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
 assert scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
 selected=set(r['selected_nodes']);assert selected=={272,273,426,427};exact=p.pair.unchanged(source,target,selected)
 arms=[i for i in n if '/arm-'in c[i]]
 for i in arms:assert np.array_equal(n[i],new[i])
 for i in [274,428]:assert np.array_equal(n[i],new[i])
 bindings=json.loads(BINDINGS.read_text());names=[node.get('name')for node in a['nodes']];selectors=[name for row in bindings['rune_motion']for name in row['bodies']]
 for name in selectors:assert names.count(name)==1
 recipe=json.loads(Path(r['native_review']).read_text());assert len(recipe['native_parts'])==12
 remainder=Path(r['native_review']).parent/'remainder.glb';rd,_=read_glb(remainder);assert scene_triangles(rd)==r['native_rune_remaining_mesh_triangles'];p.pair.unchanged(source,remainder,selected)
 assert scan.digest(remainder)==recipe['retained_mesh']['sha256']
 for part in recipe['native_parts']:
  shape=part['shape'];assert ConvexHull(np.array(shape['vertices_local_m'])).volume>0
  assert np.isfinite(shape['vertices_local_m']).all()and part['component_id'].endswith('/hub-cluster')
 original=json.loads((ROOT_OUT/'native-review/recipe.json').read_text());original_shapes={part['source_node_index']:part['shape']for part in original['native_parts']}
 for part in recipe['native_parts']:
  oldshape=original_shapes[part['source_node_index']];vertices=np.array(oldshape['vertices_local_m'])*1000+np.array(oldshape['pose']['translation_m'])*1000;eq=ConvexHull(vertices).equations
  shape=part['shape'];q=np.array(shape['vertices_local_m'])*1000+np.array(shape['pose']['translation_m'])*1000
  assert (q@eq[:,:3].T+eq[:,3]).max()<1e-4
 sweep=json.loads(Path(r['sweep_screen']).read_text())
 for row in sweep:
  if row['node']in selected:assert row['inside_witnesses']==0 and len(row['poses'])==24
 stage=json.loads((OUT/'paired-stage.json').read_text())
 for role in ['collision','visual']:
  assert sum(x['placed_triangles']for x in stage[role+'_assets'].values())==stage['placed_'+role+'_triangles']
  for x in stage[role+'_assets'].values():assert scan.digest(Path(x['path']))==x['sha256']
 exposure=json.loads((OUT/'disk-exposure-screen.json').read_text())
 assert len(exposure)==4
 for row in exposure:assert row['source_disk_hits_now_other_owner']==0 and row['candidate_earlier_over_2mm']==0
 proof=dict(center_disk_exposure_rays=sum(x['rays']for x in exposure),center_disk_first_owner_preserved=True,unchanged_mesh_owners=exact,moving_arm_mesh_owners_exact=len(arms),moving_selectors_preserved=len(selectors),rejected_large_brackets_exact=True,
  all_visual_assets_exact=True,selected_fixed_owner_count=4,native_hull_count=12,all_sections_inside_screened_original_hulls=True,no_arm_intrusion_witnesses_in_24_sampled_poses=True,continuous_clearance_proven=False,runtime_supported=False,installed=False)
 (OUT/'geometry-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
if __name__=='__main__':main()
