"""Reopen research artifacts, verify frames/counts and pin installed inputs."""
import json
from pathlib import Path
import numpy as np
from scan import ROOT,OUT,REF,digest,load_nodes,fit_boxes,box_points,FACES
from gltf_scene import read_glb,accessor


def main():
    rules=json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text())
    for path,sha in rules['pins'].items(): assert digest(Path(path))==sha,path
    ref=json.loads(REF.read_text())
    source_mesh_nodes=0
    for role,section in ref['roles'].items():
        for asset,row in section['assets'].items():
            assert digest(Path(row['path']))==row['sha256']
            if role=='collision':
                _,_,nodes=load_nodes(row['path']);source_mesh_nodes+=len(nodes)
                assert sum(map(len,nodes.values()))==row['scene_triangles']
    s=json.loads((OUT/'results.json').read_text())
    assert source_mesh_nodes==sum(s['mesh_nodes'].values())
    for row in s['boxes']:
        for b in row['box_proposals']:
            f=np.asarray(b['axes_columns']);assert np.allclose(f.T@f,np.eye(3),atol=1e-10)
            assert np.isclose(np.linalg.det(f),1)
            assert min(b['half_extents_mm'])>0
    # A rotated exact box must be found despite PCA's unequal vertex density.
    a=.37;f=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
    g=box_points(np.array([1500.,-420.,100.]),f,np.array([240.,120.,2.]))[FACES]
    assert fit_boxes(g)[0]['source_surface_max_mm']<1e-8
    previews=[]
    for collection in [json.loads((OUT/'renders.json').read_text())['subjects'],json.loads((OUT/'profiles.json').read_text())]:
        for row in collection:
            path=Path(row['preview']);assert digest(path)==row['preview_sha256']
            d,b=read_glb(path);assert d['asset']['extras']['diagnostic_only']
            assert not d['asset']['extras']['collision_approved']
            pr=d['meshes'][0]['primitives'][0];p=accessor(d,b,pr['attributes']['POSITION']);t=accessor(d,b,pr['indices']).reshape(-1,3)
            assert len(t)==row['preview_triangles'];assert np.isfinite(p).all()
            assert np.linalg.norm(np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]]),axis=1).min()>1e-14
            previews.append(dict(path=str(path),triangles=len(t),sha256=digest(path)))
    for row in json.loads((OUT/'profiles.json').read_text()):
        assert row['profile_outside_max_mm']<=row['profile_loss_limit_mm']+1e-7
        assert row['source_max_support_plane_outside_mm']<=row['profile_outside_max_mm']+1e-6
    result=dict(installed_pins_unchanged=len(rules['pins']),frozen_visual_and_collision_pins_unchanged=True,
                collision_mesh_nodes=source_mesh_nodes,screened_nodes=s['screened_nodes'],
                verified_diagnostic_previews=previews,rigid_frames_checked=True,rotated_box_sanity_passed=True,
                profile_outside_limits_passed=True,contact_approved=False)
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Verified',len(previews),'diagnostic GLBs;',source_mesh_nodes,'collision owners; installed/frozen hashes unchanged.')


if __name__=='__main__':main()
