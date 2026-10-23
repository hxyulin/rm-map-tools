"""Freeze/verify the user-reviewed slim Dart beams and top/base collision."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RULE=ROOT/'rules/collision-dart-reviewed-rmuc2027.json'
FOLDER=ROOT/'out/rmuc2027-dart-top-base'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze():
 r=json.loads((FOLDER/'verification.json').read_text());proof=json.loads((FOLDER/'geometry-verification.json').read_text());ccd=json.loads((FOLDER/'mesh-ccd-result.json').read_text());stage=json.loads((FOLDER/'paired-stage.json').read_text())
 assert proof['source_faces_contained']==10512 and proof['closed_boxes']==172 and ccd['exit_code']==0 and ccd['temporary_test_removed']
 assert sha(FOLDER/'mesh-ccd-fixture.txt')==ccd['fixture_sha256']
 assert sha(ROOT/'benchmarks/2026-10-24-dart-top-base/mesh_ccd.rs')==ccd['test_source_sha256']
 artifacts={}
 for prefix in ['rmuc2027-dart-beams-refined','rmuc2027-dart-top-base']:
  folder=ROOT/'out'/prefix
  for name in ['arena-static-collision.glb','paired-stage.json','verification.json','geometry-verification.json','deck-ray-checks.json','mesh-ccd-result.json','mesh-ccd-fixture.txt','mesh-ccd-cases.json','mesh-ccd-placement.json','mesh-ccd.log','final-verification.json']:
   p=folder/name;artifacts[f'{prefix}/{name}']=dict(path=str(p.relative_to(ROOT)),sha256=sha(p))
 for role in ['visual','collision']:
  for item in stage[role+'_assets'].values():assert sha(Path(item['path']))==item['sha256']
 rule=dict(schema_version=1,id='reviewed-dart-slim-beams-top-base-rmuc2027-20261024',base_rule='rules/collision-core-head-rune-reviewed-rmuc2027.json',user_approval='User accepted slimmer beam fit and top/base trial, withdrew the flat-sheet idea, and explicitly requested commit.',artifacts=artifacts,counts=dict(placed_visual_triangles=344792,placed_native_remaining_mesh_triangles=r['field_native_remaining_mesh_triangles'],placed_native_shapes=r['field_native_shape_counts'],placed_diagnostic_triangles=stage['placed_collision_triangles'],dart_frame_owners=9382,dart_savings_from_pre_dart_mesh=25488),policy=dict(visuals='All visual bytes exact.',sides='Reviewed slim long members with locally fitted hardware; one narrow opening remains closed.',top_base='Four top rungs and five base crossbars, flat deck and local fittings; complex mounts and guides retained.',flat_sheet=False,new_native_leaves=0),evidence=dict(side_ccd_shots=240,top_base_ccd_shots=320,top_base_replaced_faces_enclosed=10512,deck_surface_height_unchanged_rays=1554,broad_overhead_query_max_change_mm=2.5744809443644954),installed=False,runtime_timing_measured=False,constraints=['CAD meshes/fixtures remain ignored outputs; only tooling/parameters/hashes committed.','New Dart solids remain mesh-backed.','Dynamic door/traversal/full-match and mixed native-shape field integration remain unqualified.'])
 assert rule['counts']['placed_native_remaining_mesh_triangles']==361034
 RULE.write_text(json.dumps(rule,indent=2)+'\n')
def verify():
 rule=json.loads(RULE.read_text())
 for item in rule['artifacts'].values():assert sha(ROOT/item['path'])==item['sha256']
 for prefix in ['rmuc2027-dart-beams-refined','rmuc2027-dart-top-base']:
  r=json.loads((ROOT/'out'/prefix/'verification.json').read_text())
  for p,h in r['input_pins'].items():assert sha(Path(p))==h
 stage=json.loads((FOLDER/'paired-stage.json').read_text())
 for role in ['visual','collision']:
  for item in stage[role+'_assets'].values():assert sha(Path(item['path']))==item['sha256']
 print('Reviewed Dart checkpoint verified:',rule['counts'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');args=p.parse_args()
 if args.freeze:freeze()
 verify()
