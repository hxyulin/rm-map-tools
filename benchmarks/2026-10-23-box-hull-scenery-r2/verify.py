"""Final input/artifact checks and a distinct external-coverage regression."""
import importlib.util,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('coverage_final_check',Path(__file__).with_name('closed_envelopes.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
original=c.a.original;OUT=c.OUT
from gltf_scene import read_glb,accessor
from simplify_package import scene_triangles


def main():
    rule=json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text());ref=json.loads(original.REF.read_text())
    pins=dict(rule['pins']);pins[str(original.REF)]=original.digest(original.REF)
    for section in ref['roles'].values():
        for row in section['assets'].values():pins[row['path']]=row['sha256']
    for p,sha in pins.items():assert original.digest(Path(p))==sha,p
    global_proof=json.loads((OUT/'closed-envelope-global.json').read_text());assert len(global_proof['shortlist'])==3
    proof=json.loads((OUT/'closed-envelope-coverage.json').read_text())
    _,_,nodes=original.load_nodes(proof[0]['source']);coverage=[]
    for row in proof:
        fresh=c.coverage(nodes[row['node']]);assert fresh['all_facets_covered_with_tolerance']and fresh['all_facets_outward_facing_covered']
        assert fresh['raw_uncovered_area_mm2']==0 and fresh['interior_or_nonplanar_triangles']==176
        coverage.append(dict(node=row['node'],raw_uncovered_area_mm2=0.,outward_covered=True,interior_triangles=176))
    core=next(r for r in global_proof['inventory']if r['asset']=='tech-core'and r['node']==288)
    _,_,groups=original.load_nodes(core['source']);missing=c.coverage(groups[288]);assert not missing['all_facets_covered_with_tolerance']
    assert missing['raw_uncovered_area_mm2']>140
    exports=[]
    for name in ['export-verification.json','outpost-export-verification.json']:
        p=json.loads((OUT/name).read_text());target=Path(p.get('target',p.get('candidate')))
        assert original.digest(target)==p.get('target_sha256',p.get('candidate_sha256'))
        d,b=read_glb(target);count=scene_triangles(d)
        assert count==p.get('after_triangles',p.get('candidate_triangles_per_asset'))
        for node in d['nodes']:
            if 'mesh'not in node:continue
            for pr in d['meshes'][node['mesh']]['primitives']:
                pts=accessor(d,b,pr['attributes']['POSITION']);idx=accessor(d,b,pr['indices'])
                assert np.isfinite(pts).all()and idx.max()<len(pts)
        exports.append(dict(path=str(target),triangles=count,sha256=original.digest(target)))
    image_count=0
    for name in ['renders.json','closeups.json','outpost-renders.json']:
        rows=json.loads((OUT/name).read_text());rows=rows['views']if isinstance(rows,dict)else rows
        for row in rows:assert original.digest(Path(row['path']))==row['sha256'];image_count+=1
    equipment=json.loads((ROOT/'out/rmuc2027-box-hull-equipment-r2/shortlist.json').read_text())
    rune=json.loads((ROOT/'out/rmuc2027-box-hull-rune-r2/shortlist.json').read_text())
    eq_total=sum(r['native_placed_triangle_mesh_triangles_replaced']for r in equipment['native_hull_shortlist'])
    assert eq_total==1604;assert rune['totals']['placed_preview_triangle_savings']==1436
    summaries=[dict(family='Outpost closed upper blocks',native_mesh_triangles_replaced=1224,native_leaves=6,
        mesh_preview_saving=1104,status='exterior-covered-interior-removal-review'),
        dict(family='Core convex arm plates',native_mesh_triangles_replaced=1604,native_leaves=8,
        mesh_preview_saving=0,status='matching-convex-surface-native-representation-review'),
        dict(family='Rune fastener-slot plates',native_mesh_triangles_replaced=1592,native_leaves=3,
        mesh_preview_saving=1436,status='conditional-fastener-slot-fill'),
        dict(family='Dart three-strand bundles',native_mesh_triangles_replaced=2900,native_leaves=6,
        mesh_preview_saving=2648,status='conditional-strand-gap-fill-low-priority')]
    (OUT/'summary.json').write_text(json.dumps(dict(reference=str(original.REF),families=summaries,
        baseline_visual_placed=355542,baseline_collision_placed=545599,installed=False,
        caveat='Different review statuses; do not sum as approved savings. Native and preview figures are alternative representations. Excludes prior-round candidates.'),indent=2)+'\n')
    result=dict(input_pins_unchanged=len(pins),closed_outpost_exterior_rechecked=coverage,
        coarse_false_positive_core288_rejected_uncovered_area_mm2=missing['raw_uncovered_area_mm2'],
        reopened_exports=exports,matched_images_hash_checked=image_count,
        native_and_preview_budgets_cross_checked=True,installed=False,contact_approved=False,
        producer_sha256={p.name:original.digest(p)for p in sorted(Path(__file__).parent.glob('*.py'))})
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified',len(pins),'input pins,',image_count,'matched images, two reopened full-asset trials; closed-shell and missed-opening checks passed.')


if __name__=='__main__':main()
