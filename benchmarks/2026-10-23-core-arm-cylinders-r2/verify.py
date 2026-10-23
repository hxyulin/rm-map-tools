"""Independent reopen/provenance checks for expanded native arm cylinders."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from build import ROOT,OUT,PREVIOUS,prior,scan

def main():
    r=json.loads((OUT/'verification.json').read_text());source=Path(r['source_collision']);current=Path(r['previous_collision']);target=Path(r['candidate_collision'])
    for p,h in r['input_pins'].items():assert scan.digest(Path(p))==h
    assert scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
    assert scan.digest(target)==r['mesh_check']['sha256']
    unchanged=prior.pair.unchanged(current,target,set(r['changed_nodes']))
    td,tb=prior.read_glb(target);od,_,old=scan.load_nodes(source);_,components,new=scan.load_nodes(target)
    worlds={i:w for i,w,p in prior.scene_nodes(od)};overlap_checks=[]
    for row in r['trials']:
        ni=row['node'];g=new[ni];assert components[ni]=='technology-core/arm-and-shared'
        assert len(g)==row['diagnostic_triangles']==288
        np.testing.assert_allclose(g,np.concatenate([prior.cylinder(s)for s in row['cylinders']]),rtol=0,atol=.0002)
        pr=td['meshes'][td['nodes'][ni]['mesh']]['primitives'][0]
        normal=prior.accessor(td,tb,pr['attributes']['NORMAL']);assert np.isfinite(normal).all()
        np.testing.assert_allclose(np.linalg.norm(normal,axis=1),1,rtol=0,atol=2e-6)
        assert np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-9
        assert row['source_outside_native_union']['max_mm']<2.5
        assert row['exposed_round_sides_to_original']['max_mm']<7.0
        measured=prior.solid_dist(prior.probes(old[ni],30000),row['cylinders'])
        assert abs(max(0,measured.max())-row['source_outside_native_union']['max_mm'])<1e-10
        # A point strictly inside both children witnesses actual overlap, rather
        # than relying on intersecting bounding boxes or a rendered silhouette.
        edges=set()
        for j,s in enumerate(row['cylinders']):
            c=np.array(s['center_m'])*1000;a=np.array(s['axis_unit_vector']);h=s['length_m']*500
            samples=c+np.linspace(-h+1e-4,h-1e-4,101)[:,None]*a
            for k,t in enumerate(row['cylinders']):
                if j!=k and np.any(prior.solid_dist(samples,[t])< -1e-6):edges.add(tuple(sorted([j,k])))
        reached={0}
        for _ in range(3):
            for j,k in edges:
                if j in reached or k in reached:reached.update([j,k])
        assert reached=={0,1,2}
        overlap_checks.append(dict(node=ni,overlap_witness_edges=sorted(edges),connected_compound=True))
    # Earlier accepted joints stay exactly as they were in the preview.
    assert all(i not in r['changed_nodes']for i in [5,18,22,25])
    native=json.loads((OUT/'native/collision-shapes.json').read_text());nd,nb=prior.read_glb(OUT/'native/remainder.glb')
    assert native['source']['sha256']==scan.digest(source)
    assert native['retained_mesh']['sha256']==scan.digest(OUT/'native/remainder.glb')
    assert native['replaced_node_indices']==r['all_native_nodes']==[5,17,18,22,25,26,30,37]
    assert len(native['native_parts'])==r['native_cylinders_per_core']==21
    assert native['retained_mesh']['triangles']==prior.scene_triangles(nd)==52006
    assert native['removed_mesh_triangles']==16482
    retained_exact=prior.pair.unchanged(source,OUT/'native/remainder.glb',set(r['all_native_nodes']))
    parents={i:p for i,w,p in prior.scene_nodes(od)}
    for part in native['native_parts']:
        ni=part['source_node_index'];s=part['shape'];assert part['source_node_name']==od['nodes'][ni]['name']
        assert np.array_equal(worlds[ni],np.eye(4))
        assert 'mesh'not in nd['nodes'][ni]
        ancestors=[];a=ni
        while a is not None:ancestors.append(a);a=parents[a]
        assert ancestors[::-1]==part['ancestor_nodes_root_first']
        np.testing.assert_allclose(Rotation.from_quat(s['pose']['rotation_xyzw']).apply([0,0,1]),s['axis_unit_vector'],rtol=0,atol=1e-12)
        assert min(s['radius_m'],s['length_m'])>0 and np.isfinite([s['radius_m'],s['length_m']]).all()
        preview=prior.cylinder(dict(center_m=s['pose']['translation_m'],axis_unit_vector=s['axis_unit_vector'],radius_m=s['radius_m'],length_m=s['length_m']))
        vertices,idx=np.unique(preview.reshape(-1,3),axis=0,return_inverse=True);tri=idx.reshape(-1,3)
        edges=np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1)
        _,counts=np.unique(edges,axis=0,return_counts=True);assert (counts==2).all()
        assert np.einsum('ij,ij->i',preview[:,0],np.cross(preview[:,1],preview[:,2])).sum()>0
    previous=json.loads((PREVIOUS/'native/collision-shapes.json').read_text())
    existing={p['id']:p['shape']for p in previous['native_parts']}
    for part in native['native_parts']:
        if part['id']in existing:assert part['shape']==existing[part['id']]
    stage=json.loads((OUT/'paired-stage.json').read_text());old_stage=json.loads((PREVIOUS/'paired-stage.json').read_text())
    assert stage['visual_assets']==old_stage['visual_assets']
    for asset,entry in old_stage['collision_assets'].items():
        if asset!='tech-core':assert stage['collision_assets'][asset]==entry
    for role in ['visual','collision']:
        assert sum(v['placed_triangles']for v in stage[f'{role}_assets'].values())==stage[f'placed_{role}_triangles']
        for entry in stage[f'{role}_assets'].values():assert scan.digest(Path(entry['path']))==entry['sha256']
    assert r['remaining_arm_native_mesh_per_core']==6609
    assert r['field_native_remaining_mesh_triangles']==479293
    renders=json.loads((OUT/'renders.json').read_text());assert len(renders['views'])==48
    for v in renders['views']:assert scan.digest(Path(v['path']))==v['sha256']
    assert scan.digest(Path(renders['placement_manifest']))==renders['placement_manifest_sha256']
    artifact_hashes={str(p.relative_to(OUT)):scan.digest(p)for p in OUT.rglob('*')if p.is_file()and p.name not in ['final-verification.json','gallery.html']}
    output=dict(prior_candidate_and_installed_inputs_exact=True,approved_visual_file_exact=True,previous_nine_cylinder_shapes_exact=True,
        unselected_preview_mesh_owners_exact=unchanged,unselected_native_source_mesh_owners_exact=retained_exact,
        source_owner_names_ancestry_transforms_and_all_materials_exact=True,native_cylinder_count_per_core=21,
        new_compound_overlap_checks=overlap_checks,
        native_mesh_triangles_per_core=52006,remaining_arm_mesh_triangles_per_core=6609,matched_render_count=48,
        artifact_sha256=artifact_hashes,contact_validated=False,installed=False)
    (OUT/'final-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Verified 21 native cylinders/Core, unchanged approved visuals,',unchanged,'exact other owners, 48 matched renders.')

if __name__=='__main__':main()
