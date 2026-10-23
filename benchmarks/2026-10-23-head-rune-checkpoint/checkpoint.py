"""Freeze/verify the explicitly approved head and projectile-covering Rune hub."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RULE=ROOT/'rules/collision-core-head-rune-reviewed-rmuc2027.json'
HEAD=ROOT/'out/rmuc2027-core-head-rod-base-plate/rod-base-plate/verification.json'
RUNE=ROOT/'out/rmuc2027-rune-hub-projectile-cover/verification.json'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def record(path):return dict(path=str(path.relative_to(ROOT))if path.is_relative_to(ROOT)else str(path),sha256=sha(path))
def resolve(path):return ROOT/path if not Path(path).is_absolute()else Path(path)

def freeze():
 head=json.loads(HEAD.read_text());rune=json.loads(RUNE.read_text());folder=RUNE.parent;proof=json.loads((folder/'geometry-verification.json').read_text());ccd=json.loads((folder/'native-ccd-result.json').read_text());stage=json.loads((folder/'paired-stage.json').read_text())
 assert proof['source_triangles_fully_enclosed']==18135 and proof['closed_reopened_preview_hulls']==13
 assert sum(x['misses']for x in proof['ray_checks'])==0 and ccd['exit_code']==0 and ccd['temporary_test_removed']
 assert sha(folder/'native-ccd-fixture.txt')==ccd['fixture_sha256']
 assert sha(ROOT/'benchmarks/2026-10-23-rune-hub-projectile-cover/native_ccd.rs')==ccd['test_source_sha256']
 assert len(json.loads((folder/'native-ccd-cases.json').read_text()))*4==376
 artifacts={}
 for label,report,path in [('core_head',head,HEAD),('rune_hub',rune,RUNE)]:
  native=Path(report['native_review']);files=dict(report=path,collision=Path(report['candidate_collision']),native_recipe=native,native_remainder=native.parent/'remainder.glb',visual=Path(report['unchanged_visual']),geometry_proof=path.parent/'geometry-verification.json')
  for source,h in report['input_pins'].items():assert sha(Path(source))==h
  assert sha(files['collision'])==report['candidate_sha256']and sha(files['visual'])==report['unchanged_visual_sha256']
  artifacts[label]={name:record(file)for name,file in files.items()}
 for name in ['native-ccd-result.json','native-ccd-fixture.txt','native-ccd-cases.json','native-ccd.log','triangle-assignments.json','paired-stage.json','final-verification.json']:
  artifacts.setdefault('rune_evidence',{})[name]=record(folder/name)
 for role in ['visual','collision']:
  assert sum(x['placed_triangles']for x in stage[role+'_assets'].values())==stage['placed_'+role+'_triangles']
  for data in stage[role+'_assets'].values():assert sha(Path(data['path']))==data['sha256']
 rule=dict(schema_version=1,id='reviewed-core-head-and-projectile-covering-rune-hub-rmuc2027-20261023',user_approval='User accepted the Core head, accepted the final Rune spoke/filled-center shape and conservative projectile coverage, then explicitly requested commit and continuation.',
  base_core_arm_rule='rules/collision-core-arm-reviewed-rmuc2027.json',artifacts=artifacts,
  counts=dict(placed_visual_triangles=344792,placed_native_remaining_mesh_triangles=rune['field_native_mesh_triangles'],placed_native_shapes=rune['field_native_shape_counts'],placed_diagnostic_triangles=stage['placed_collision_triangles'],core_head_mesh_per_unit=head['head_mesh_triangles_kept'],core_head_native_shapes_per_unit=head['head_native_shapes'],rune_remaining_mesh=rune['native_rune_remaining_mesh_triangles'],rune_hub_native_hulls=13,rune_hub_remaining_mesh=0),
  policies=dict(visuals='Existing approved visual asset bytes stay exact.',core_head='Approved coarse fixed internals and rod/plate fits; original front/outer skin retained with simplified side recesses.',rune_hub='Five short spoke hulls and one filled center per bank plus one reverse bracket hull. Every original hub triangle is wholly enclosed by one convex solid; previous hulls also enclosed.',coverage_padding_mm=.25,source_face_normal_merge_degrees=5,center_polygon_sides=12,old_rune_5mm_axial_clearance_claim_withdrawn=True),
  hub_evidence=dict(source_triangles_fully_enclosed=18135,reopened_margin_min_mm=proof['reopened_glb_triangle_margin_min_mm'],directional_rays=sum(x['rays']for x in proof['ray_checks']),directional_misses=0,native_ccd_trajectories=94,native_ccd_shots=376,native_ccd_passed=True),
  constraints=['Only tooling/parameters/hashes committed; CAD-derived meshes/fixtures remain ignored outputs.','Grouped mixed-shape native field loading and full-match kinematic/scoring validation remain outstanding.','Native CCD evidence applies to fixed Rune hub shapes directly in WorldPhysics, not the entire field.','No speedup measured; native shape count remains separate from mesh triangle count.'],runtime_supported=False,installed=False)
 assert rule['counts']['placed_native_remaining_mesh_triangles']==386522 and rule['counts']['placed_native_shapes']==dict(cylinder=80,box=8,convex_hull=33)
 RULE.write_text(json.dumps(rule,indent=2)+'\n')

def verify():
 rule=json.loads(RULE.read_text());count=0
 for group in rule['artifacts'].values():
  for item in group.values():assert sha(resolve(item['path']))==item['sha256'];count+=1
 rune=json.loads(resolve(rule['artifacts']['rune_hub']['report']['path']).read_text());head=json.loads(resolve(rule['artifacts']['core_head']['report']['path']).read_text())
 for report in [rune,head]:
  for path,h in report['input_pins'].items():assert sha(Path(path))==h
 stage=json.loads(resolve(rule['artifacts']['rune_evidence']['paired-stage.json']['path']).read_text())
 for role in ['visual','collision']:
  for item in stage[role+'_assets'].values():assert sha(Path(item['path']))==item['sha256']
 assert stage['placed_collision_triangles']==rule['counts']['placed_diagnostic_triangles']
 print('Frozen checkpoint verified:',count,'review artifacts;',rule['counts'])
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');args=parser.parse_args()
 if args.freeze:freeze()
 verify()
