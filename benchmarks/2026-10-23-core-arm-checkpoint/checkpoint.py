"""Reproduce the reviewed Core arm/base directly from pinned installed GLBs.

Commit only parameters, scripts and hashes. CAD meshes remain ignored outputs.
The complete field review stage is context, not a runtime installation contract.
"""
import argparse,copy,importlib.util,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('core_arm_recipe_helpers',ROOT/'benchmarks/2026-10-23-core-arm-proxies/build.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
OUT=ROOT/'out/rmuc2027-core-arm-checkpoint'
RULE=ROOT/'rules/collision-core-arm-reviewed-rmuc2027.json'
REVIEW=ROOT/'out/rmuc2027-core-joints-base-r3'

def source_paths(rule):
    ref=json.loads(p.scan.REF.read_text());sources={role:Path(ref['roles'][role]['assets']['tech-core']['path'])for role in ['visual','collision']}
    for role,path in sources.items():assert p.scan.digest(path)==rule['source_sha256'][role]
    return sources

def build(rule):
    sources=source_paths(rule);OUT.mkdir(exist_ok=True)
    replacements={row['node_index']:np.concatenate([p.cylinder(s)for s in row['cylinders']])for row in rule['native_selection']['replacements']}
    vd,vc,vn=p.scan.load_nodes(sources['visual']);cd,cc,cn=p.scan.load_nodes(sources['collision'])
    for row in rule['native_selection']['replacements']:
        ni=row['node_index'];assert cd['nodes'][ni]['name']==row['node_name']and cc[ni]in ['technology-core/arm-and-shared','technology-core/pedestal-and-shoulder']
    visual={};normals={}
    for row in rule['visual_tubes']:
        ni=row['visual_node'];assert vd['nodes'][ni]['name']==row['source_name']
        g=p.revolve(np.array(row['center_mm']),row['axis'],row['profile_mm'],row['segments']);visual[ni]=g
        normals[ni]=p.smooth_profile_normals(g,row['center_mm'],row['axis'],row['profile_mm'],row['segments'])
    v=p.replace(sources['visual'],OUT/'visual-tech-core.glb',visual,normals)
    c=p.replace(sources['collision'],OUT/'collision-tech-core.glb',replacements)
    native=p.export_native(sources['collision'],rule['native_selection'],OUT/'native')
    assert [v['after'],c['after'],native['retained_mesh']['triangles'],len(native['native_parts'])]==[26123,51297,47553,39]
    return dict(visual=v,collision=c,native_remaining_mesh_triangles=47553,native_cylinders=39,
        files={name:p.scan.digest(OUT/name)for name in ['visual-tech-core.glb','collision-tech-core.glb','native/remainder.glb','native/collision-shapes.json']})

def compare_review():
    report=json.loads((REVIEW/'verification.json').read_text());checks={}
    for role,path in [('visual',report['unchanged_visual']),('collision',report['candidate_collision'])]:
        target=OUT/f'{role}-tech-core.glb'
        # Primitive/accessor payloads are identical, while mesh/accessor indices
        # can be compacted differently by canonical one-pass reconstruction.
        checks[role]=p.pair.unchanged(Path(path),target,set())
    return checks

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',action='store_true');args=ap.parse_args()
    if args.freeze:
        r=json.loads((REVIEW/'verification.json').read_text());first=json.loads((ROOT/'out/rmuc2027-core-arm-proxies/verification.json').read_text())
        rule=dict(schema_version=1,id='reviewed-core-arm-and-mount-rmuc2027-20261023',reference='rules/manual-review-reference-rmuc2027.json',
            user_approval='User accepted the arm, joint covers and three-cylinder mounting base and explicitly requested commit. Visual review approval; runtime/contact qualification remains outstanding.',
            source_sha256={role:p.scan.digest(Path(first['sources'][role]))for role in ['visual','collision']},
            native_selection=json.loads((REVIEW/'native-selection.json').read_text()),visual_tubes=first['tubes'],
            reviewed_files={key:dict(path=str(Path(r[key]).relative_to(ROOT)),sha256=p.scan.digest(Path(r[key])))for key in ['candidate_collision','unchanged_visual']},
            reviewed_evidence=dict(path=str((REVIEW/'final-verification.json').relative_to(ROOT)),sha256=p.scan.digest(REVIEW/'final-verification.json')),
            counts_per_core=dict(visual=26123,collision_preview=51297,native_remaining_mesh=47553,native_cylinders=39,remaining_arm_mesh=3354),
            protected='All visual geometry except the two approved arm tube profiles stays exact. Head collision, rectangular pedestal and squared elbow connector remain exact.',
            intentional_losses=['Joint, tube and mounting bores/access openings filled in collision.','Small fasteners, ports and fillets approximated; base tab rounded.'],
            excluded=['node 27 squared elbow cylinder trial','earlier aggressive visual shell trials','other native hull alternatives'],installed=False,contact_validated=False)
        result=build(rule);rule['reviewed_payload_comparison']=compare_review();rule['canonical_outputs']=result
        RULE.write_text(json.dumps(rule,indent=2)+'\n')
    else:
        rule=json.loads(RULE.read_text());result=build(rule);assert result==rule['canonical_outputs']
    for path,h in json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text())['pins'].items():assert p.scan.digest(Path(path))==h
    (OUT/'verification.json').write_text(json.dumps(dict(rule=str(RULE.relative_to(ROOT)),rule_sha256=p.scan.digest(RULE),**result,installed=False,contact_validated=False),indent=2)+'\n')
    print('Reviewed Core checkpoint verified: 26,123 visual; 51,297 collision preview; native 47,553 mesh + 39 cylinders per Core.')

if __name__=='__main__':main()
