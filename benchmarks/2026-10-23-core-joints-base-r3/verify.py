"""Reopen geometry, owner selections and the three-cylinder base compound."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from build import ROOT,OUT,PREVIOUS,p,r2,scan,CAPS

def main():
    r=json.loads((OUT/'verification.json').read_text());source=Path(r['source_collision']);target=Path(r['candidate_collision'])
    for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h
    assert scan.digest(Path(r['unchanged_visual']))==r['unchanged_visual_sha256']
    assert scan.digest(target)==r['mesh_check']['sha256']
    exact=p.pair.unchanged(Path(r['previous_collision']),target,set(r['changed_nodes']))
    assert set(r['changed_nodes'])==set(CAPS)|{72}and 27 not in r['changed_nodes']
    od,oc,on=scan.load_nodes(source);td,tb=p.read_glb(target);_,_,new=scan.load_nodes(target)
    for row in r['trials']:
        ni=row['node'];g=new[ni];assert len(row['cylinders'])==(3 if ni==72 else 1)
        np.testing.assert_allclose(g,np.concatenate([p.cylinder(s)for s in row['cylinders']]),rtol=0,atol=.0002)
        assert np.isfinite(g).all()and np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-9
        normals=p.accessor(td,tb,td['meshes'][td['nodes'][ni]['mesh']]['primitives'][0]['attributes']['NORMAL'])
        np.testing.assert_allclose(np.linalg.norm(normals,axis=1),1,rtol=0,atol=2e-6)
        error=p.solid_dist(p.probes(on[ni],20000),row['cylinders']);assert abs(max(0,error.max())-row['source_outside_union']['max_mm'])<1e-10
        assert error.max()<(1. if ni==72 else 3.)
        assert row['exposed_sides_to_source']['max_mm']<(11. if ni==72 else 7.)
    native=json.loads((OUT/'native/collision-shapes.json').read_text());nd,_=p.read_glb(OUT/'native/remainder.glb')
    assert native['source']['sha256']==scan.digest(source)
    assert native['retained_mesh']['sha256']==scan.digest(OUT/'native/remainder.glb')
    assert len(native['native_parts'])==r['native_cylinders_per_core']==39
    assert native['retained_mesh']['triangles']==p.scene_triangles(nd)==47553
    assert len(native['replaced_node_indices'])==24 and 27 not in native['replaced_node_indices']
    assert native['replaced_node_indices']==r['all_native_nodes']
    retained_exact=p.pair.unchanged(source,OUT/'native/remainder.glb',set(r['all_native_nodes']))
    old_native=json.loads((PREVIOUS/'native/collision-shapes.json').read_text());old_shapes={x['id']:x['shape']for x in old_native['native_parts']}
    parents={i:parent for i,w,parent in p.scene_nodes(od)}
    for part in native['native_parts']:
        ni=part['source_node_index'];s=part['shape'];assert part['source_node_name']==od['nodes'][ni]['name']and 'mesh'not in nd['nodes'][ni]
        ancestors=[];j=ni
        while j is not None:ancestors.append(j);j=parents[j]
        assert ancestors[::-1]==part['ancestor_nodes_root_first']
        np.testing.assert_allclose(Rotation.from_quat(s['pose']['rotation_xyzw']).apply([0,0,1]),s['axis_unit_vector'],rtol=0,atol=1e-12)
        assert min(s['radius_m'],s['length_m'])>0
        if part['id']in old_shapes:assert part['shape']==old_shapes[part['id']]
    # Strict interior points witness connection of all three base cylinders.
    base=next(x for x in r['trials']if x['node']==72)['cylinders'];edges=set()
    for j,s in enumerate(base):
        center=np.array(s['center_m'])*1000;a,u,v=p.basis(s['axis_unit_vector']);radius=s['radius_m']*1000;h=s['length_m']*500
        angle=np.arange(32)*2*np.pi/32;radial=np.cos(angle)[:,None]*u+np.sin(angle)[:,None]*v
        points=np.concatenate([(center+np.linspace(-h*.999,h*.999,17)[:,None,None]*a+fraction*radius*radial[None,:,:]).reshape(-1,3)for fraction in [0,.5,.9]])
        for k,t in enumerate(base):
            if j!=k and (p.solid_dist(points,[t])< -1e-6).any():edges.add(tuple(sorted([j,k])))
    connected={0}
    for _ in range(3):
        for j,k in edges:
            if j in connected or k in connected:connected.update([j,k])
    assert connected=={0,1,2}
    stage=json.loads((OUT/'paired-stage.json').read_text());before=json.loads(Path(r['previous_stage']).read_text())
    assert stage['visual_assets']==before['visual_assets']
    for asset,entry in before['collision_assets'].items():
        if asset!='tech-core':assert stage['collision_assets'][asset]==entry
    for role in ['visual','collision']:
        assert sum(x['placed_triangles']for x in stage[f'{role}_assets'].values())==stage[f'placed_{role}_triangles']
        for entry in stage[f'{role}_assets'].values():assert scan.digest(Path(entry['path']))==entry['sha256']
    assert r['field_preview_triangles']==477875 and r['field_native_mesh_triangles']==470387
    renders=json.loads((OUT/'renders.json').read_text());assert len(renders['views'])==48
    for row in renders['views']:assert scan.digest(Path(row['path']))==row['sha256']
    reject=r['rejected_connector'];assert scan.digest(Path(reject['path']))==reject['sha256']
    hashes={str(x.relative_to(OUT)):scan.digest(x)for x in OUT.rglob('*')if x.is_file()and x.name not in ['final-verification.json','gallery.html']}
    output=dict(approved_visual_file_exact=True,previous_21_native_shapes_exact=True,unchanged_preview_owners_exact=exact,
        unchanged_native_source_owners_exact=retained_exact,native_cylinders_per_core=39,base_overlap_edges=sorted(edges),
        base_compound_connected=True,rectangular_pedestal_and_protected_head_exact=True,squared_elbow_connector_retained=True,
        source_names_ancestry_materials_transforms_exact=True,matched_render_count=48,artifact_sha256=hashes,installed=False,contact_validated=False)
    (OUT/'final-verification.json').write_text(json.dumps(output,indent=2)+'\n')
    print('Verified 39 native cylinders/Core; base connected; visual exact;',exact,'other preview owners exact.')

if __name__=='__main__':main()
