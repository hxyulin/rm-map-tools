"""Freeze or verify the explicitly accepted Outpost/Rune collision trials."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];FOLDER=ROOT/'out/rmuc2027-outpost-rune-next';RULE=ROOT/'rules/collision-outpost-rune-arms-reviewed-rmuc2027.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze():
 summary=json.loads((FOLDER/'summary.json').read_text());proof=json.loads((FOLDER/'geometry-verification.json').read_text());ccd=json.loads((FOLDER/'mesh-ccd-result.json').read_text());stage=json.loads((FOLDER/'paired-stage.json').read_text())
 assert summary['placed_triangles_saved']==26888 and summary['field_native_remaining_mesh_triangles']==334146
 assert ccd['exit_code']==0 and ccd['temporary_test_removed'] and sha(FOLDER/'mesh-ccd-fixture.txt')==ccd['fixture_sha256']
 assert sha(ROOT/'benchmarks/2026-10-24-outpost-rune-next/mesh_ccd.rs')==ccd['test_source_sha256']
 assert len(json.loads((FOLDER/'mesh-ccd-cases.json').read_text()))*4==1392
 artifacts={}
 for name in ['outpost-collision.glb','rune-collision.glb','outpost-verification.json','rune-verification.json','paired-stage.json','summary.json','geometry-verification.json','mesh-ccd-result.json','mesh-ccd-fixture.txt','mesh-ccd-cases.json','mesh-ccd-placement.json','mesh-ccd.log','final-verification.json']:
  p=FOLDER/name;artifacts[name]=dict(path=str(p.relative_to(ROOT)),sha256=sha(p))
 rule=dict(schema_version=1,id='reviewed-outpost-hardware-and-rune-strips-rmuc2027-20261024',base_rule='rules/collision-dart-reviewed-rmuc2027.json',user_approval='User accepted the Outpost hardware and Rune strip collision trials, then explicitly requested commit.',artifacts=artifacts,counts=summary,policy=dict(outpost='134 compact hardware boxes per unit in owners 14/23/25; broad shells and separate rotor/armor owners exact.',rune='20 slender profile owners across ten rotating arms; concave outline retained; small bores filled; original motion ownership preserved.',visuals='All protected and other visual bytes unchanged.',new_native_leaves=0),evidence=dict(source_faces_enclosed=dict(outpost=7530,rune=15736),closed_solids_per_asset=dict(outpost=134,rune=20),static_ccd_shots=1392,static_ccd_passed=True,max_sampled_reverse_mm={asset:proof[asset]['max_sampled_reverse_mm']for asset in proof}),constraints=['Only tooling/parameters/hashes committed; CAD meshes and fixtures stay ignored.','New shapes remain mesh-backed; Rune native hub remainder/sidecar not rebuilt by this trial.','Separated static CCD fixtures do not qualify live rotating-body collision, scoring or whole-field integration.','Not installed; runtime timing unmeasured.'],installed=False)
 RULE.write_text(json.dumps(rule,indent=2)+'\n')
def verify():
 rule=json.loads(RULE.read_text())
 for item in rule['artifacts'].values():assert sha(ROOT/item['path'])==item['sha256']
 for asset in ['outpost','rune']:
  r=json.loads((FOLDER/f'{asset}-verification.json').read_text())
  for p,h in r['input_pins'].items():assert sha(Path(p))==h
 stage=json.loads((FOLDER/'paired-stage.json').read_text())
 for role in ['visual','collision']:
  for item in stage[role+'_assets'].values():assert sha(Path(item['path']))==item['sha256']
 assert stage['placed_collision_triangles']==rule['counts']['field_diagnostic_triangles']
 print('Reviewed Outpost/Rune checkpoint verified:',rule['counts'])
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');a=p.parse_args()
 if a.freeze:freeze()
 verify()
