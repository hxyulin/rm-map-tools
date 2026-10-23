"""Reopen input identities/counts and recompute shortlisted geometric evidence."""
import json
from pathlib import Path
import numpy as np
from scan import ROOT, OUT, sha, evaluate, serial
from gltf_scene import read_glb, scene_nodes, mesh_instances
from report import geometry

def main():
    review=json.loads((ROOT/'out/rmuc2027-installed-reference-review/review.json').read_text())
    summary=json.loads((OUT/'shortlist.json').read_text());scan=json.loads((OUT/'classified-scan.json').read_text())
    assert summary['scan_sha256']==sha(OUT/'scan.json')
    checks=[]; pins={}
    for asset,meta in review['roles']['collision']['assets'].items():
        p=ROOT/'out/rmuc2027-installed-reference-review/reference/collision'/f'{asset}.glb';assert sha(p)==meta['sha256'];pins[str(p.relative_to(ROOT))]=sha(p)
        d,b=read_glb(p);world={i:w for i,w,_ in scene_nodes(d)};counts={}
        for i,_,points,t,_ in mesh_instances(d,b):counts[i]=counts.get(i,0)+len(t)
        assert sum(counts.values())==meta['scene_triangles']
        for r in scan['candidates']:
            if r['asset']!=asset:continue
            assert d['nodes'][r['node']]['name']==r['node_name']
            assert counts[r['node']]==r['source_triangles']
            assert r['placed_source_triangles']==counts[r['node']]*meta['placements']
            assert np.array_equal(world[r['node']],r['node_world_matrix'])
            assert r['ancestry'][-1]['index']==r['node']
            assert not r['contact_approved']
        checks.append(dict(asset=asset,reopened_triangles=sum(counts.values()),verified_scanned_nodes=sum(r['asset']==asset for r in scan['candidates'])))
    for p,h in summary['manifest_pins'].items():assert sha(Path(p))==h
    rechecks=[]
    for r in summary['candidates']:
        p,t=geometry(ROOT/r['source'],r['node']);f=next(f for f in r['fits'] if f['shape']['kind']==r['best_kind']);m=evaluate(p,t,f['shape'])
        for key in ['forward_outside_solid','forward_absolute_surface','reverse_surface']:
            assert abs(m[key]['max_mm']-f['metrics'][key]['max_mm'])<1e-8
            assert m[key]['samples']==f['metrics'][key]['samples']
        w=np.asarray(r['node_world_matrix']);sh=f['shape']
        assert np.allclose(w[:3,:3]@sh['center_node_local_m']+w[:3,3],sh['center_m'],atol=1e-12)
        assert len(sh['placed_source_arena_poses'])==r['placements']
        rechecks.append(dict(asset=r['asset'],node=r['node'],max_mm=r['strict_bidirectional_max_mm'],source_triangles=len(t),native_shapes=1))
    renders=json.loads((OUT/'renders.json').read_text())
    for r in renders:assert sha(ROOT/r['path'])==r['sha256']
    assert len(renders)==36
    assert len({(r['asset'],r['node']) for r in summary['candidates']})==4
    assert sum(r['placed_source_triangles'] for r in summary['candidates'])==2528
    assert all(not (r['asset']=='tech-core' and r['node']==22) for r in summary['candidates'])
    result=dict(passed=True,frozen_inputs=pins,source_checks=checks,shortlist_metric_rechecks=rechecks,matched_render_hashes_checked=len(renders),manifest_pins_checked=len(summary['manifest_pins']),script_hashes={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},scope='Finite research evidence only; no contact approval, runtime changes, build or install.')
    (OUT/'verification.json').write_text(json.dumps(result,indent=2,default=serial)+'\n')
    print('Verified six frozen collision GLBs, 214 node identities/counts, four native-fit metrics, two manifests, 36 renders. No Core22 duplicate savings.')

if __name__=='__main__':main()
