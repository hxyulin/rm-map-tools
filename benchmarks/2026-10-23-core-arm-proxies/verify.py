"""Reopen geometry and verify the paired/native variants independently."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from build import ROOT,OUT,scan,pair,read_glb,scene_nodes,scene_triangles,cylinder,accessor

def topology(g):
    p,idx=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);t=idx.reshape(-1,3)
    edges=np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]);_,count=np.unique(np.sort(edges,axis=1),axis=0,return_counts=True)
    return dict(boundary_edges=int((count==1).sum()),nonmanifold_edges=int((count>2).sum()),
        signed_volume_mm3=float(np.einsum('ij,ij->i',g[:,0],np.cross(g[:,1],g[:,2])).sum()/6))

def main():
    r=json.loads((OUT/'verification.json').read_text());render=json.loads((OUT/'renders.json').read_text());stage=json.loads((OUT/'paired-stage.json').read_text())
    for p,h in r['input_pins'].items():assert scan.digest(Path(p))==h
    visual=Path(r['visual_candidate']);collision=Path(r['collision_candidate'])
    assert scan.digest(visual)==r['visual']['sha256'];assert scan.digest(collision)==r['collision']['sha256']
    visual_nodes=scan.load_nodes(visual)[2];collision_nodes=scan.load_nodes(collision)[2]
    changed={'visual':{15,24},'collision':{5,17,18,22,25,26}}
    exact={role:pair.unchanged(Path(r['sources'][role]),Path(r[f'{role}_candidate']),changed[role])for role in changed}
    for role in changed:
        d,b=read_glb(r[f'{role}_candidate']);nodes=scan.load_nodes(Path(r[f'{role}_candidate']))[2]
        for ni in changed[role]:
            g=nodes[ni];assert np.isfinite(g).all();assert np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-9
            for pr in d['meshes'][d['nodes'][ni]['mesh']]['primitives']:
                normals=accessor(d,b,pr['attributes']['NORMAL']);assert np.isfinite(normals).all()
                np.testing.assert_allclose(np.linalg.norm(normals,axis=1),1,rtol=0,atol=2e-6)
        assert scene_triangles(d)==r[role]['after']
    tube_checks=[]
    for row in r['tubes']:
        g=collision_nodes[row['collision_node']];assert np.array_equal(g,visual_nodes[row['visual_node']])
        top=topology(g);assert top['boundary_edges']==64 and top['nonmanifold_edges']==0
        a=np.array(row['axis']);c=np.array(row['center_mm']);q=g.mean(1)-c;rad=q-(q@a)[:,None]*a
        normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);axial_span=np.ptp((g-c)@a,axis=1)
        assert (np.einsum('ij,ij->i',normal,rad)[axial_span>.001]>0).all()
        tube_checks.append(dict(node=row['collision_node'],**top,open_end_boundary_edges_preserved=True,outward_normals=True))
    native=json.loads((OUT/'native/collision-shapes.json').read_text());native_source=OUT/'tube-profile-collision.glb';rem=OUT/'native/remainder.glb'
    assert native['source']['sha256']==scan.digest(native_source);assert native['retained_mesh']['sha256']==scan.digest(rem)
    assert native['replaced_node_indices']==[5,18,22,25];assert len(native['native_parts'])==9
    nd,_=read_glb(native_source);rd,_=read_glb(rem)
    assert all('mesh'not in rd['nodes'][i]for i in native['replaced_node_indices'])
    assert scene_triangles(rd)==native['retained_mesh']['triangles']==56102
    native_unchanged=pair.unchanged(native_source,rem,set(native['replaced_node_indices']))
    parents={i:p for i,w,p in scene_nodes(nd)};cylinder_checks=[]
    for part in native['native_parts']:
        ni=part['source_node_index'];s=part['shape'];assert part['source_node_name']==nd['nodes'][ni]['name']
        ancestors=[];n=ni
        while n is not None:ancestors.append(n);n=parents[n]
        assert ancestors[::-1]==part['ancestor_nodes_root_first']
        axis=np.array(s['axis_unit_vector']);quat=np.array(s['pose']['rotation_xyzw'])
        np.testing.assert_allclose(Rotation.from_quat(quat).apply([0,0,1]),axis,rtol=0,atol=1e-12)
        assert np.isfinite([s['radius_m'],s['length_m']]).all()and min(s['radius_m'],s['length_m'])>0
        simple=dict(center_m=s['pose']['translation_m'],axis_unit_vector=axis,radius_m=s['radius_m'],length_m=s['length_m'])
        topo=topology(cylinder(simple));assert topo['boundary_edges']==topo['nonmanifold_edges']==0 and topo['signed_volume_mm3']>0
        cylinder_checks.append(dict(id=part['id'],owner=ni,**topo))
    for v in render['views']:assert scan.digest(Path(v['path']))==v['sha256']
    assert len(render['views'])==66
    assert scan.digest(Path(render['source_arm_native_glb']))==render['source_arm_native_sha256']
    assert scan.digest(Path(render['placement_manifest']))==render['placement_manifest_sha256']
    native_path=Path(render['source_arm_native_glb']);meta=json.loads(native_path.with_name('native.json').read_text())
    assert scan.digest(native_path.with_name('source.step'))==meta['source_step_sha256']
    for role in changed:
        assert sum(x['placed_triangles']for x in stage[f'{role}_assets'].values())==stage[f'placed_{role}_triangles']
        for info in stage[f'{role}_assets'].values():assert scan.digest(Path(info['path']))==info['sha256']
    # Every copied stage entry except Core must match the accepted prior pair.
    before=json.loads(Path(r['previous_pair_stage']).read_text())
    for role in changed:
        for asset,entry in before[f'{role}_assets'].items():
            if asset!='tech-core':assert stage[f'{role}_assets'][asset]==entry
    artifact_sha={str(p.relative_to(OUT)):scan.digest(p)for p in OUT.rglob('*')if p.is_file()and p.name not in ['final-verification.json','gallery.html']}
    output=dict(unchanged_mesh_owners_exact=exact,native_retained_mesh_owners_exact=native_unchanged,tube_checks=tube_checks,
        native_cylinder_checks=cylinder_checks,render_count=len(render['views']),protected_visibility=render['protected_visibility'],
        previous_non_core_stage_entries_exact=True,original_installed_pins_exact=True,artifact_sha256=artifact_sha,
        status='geometry_and_provenance_verified_review_candidate',contact_validated=False,runtime_installed=False)
    (OUT/'final-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Verified paired outputs, 9 native cylinders, unchanged owners',exact,'and',len(render['views']),'matched images.')

if __name__=='__main__':main()
