"""Reopen-qualified Rune plate trial applied on the reviewed R2 checkpoint."""
import copy,json,sys
from pathlib import Path
import numpy as np
from trial import ROOT,OUT,scan,topology,samples
from gltf_scene import read_glb,write_glb,scene_nodes,accessor
from simplify_package import append_accessor,compact,scene_triangles
from mesh_quality import distances


def main():
    baseline=ROOT/'out/rmuc2027-collision-review-checkpoint/collision/rune.glb'
    stage_path=ROOT/'out/rmuc2027-collision-review-checkpoint/stage.json';stage=json.loads(stage_path.read_text())
    assert scan.digest(baseline)==stage['assets']['rune']['sha256']
    result=json.loads((OUT/'results.json').read_text());source=Path(result['source']);assert scan.digest(source)==result['source_sha256']
    doc,blob=read_glb(baseline);candidate=copy.deepcopy(doc);binary=bytearray(blob)
    _,_,original=scan.load_nodes(source);_,_,base=scan.load_nodes(baseline)
    worlds={i:w for i,w,_ in scene_nodes(doc)};records=[];changed=set()
    for row in result['rows']:
        if row['status']!='candidate':continue
        ni=row['node'];assert np.array_equal(original[ni],base[ni]),'overlaps an earlier accepted change'
        z=np.load(OUT/f'node-{ni}.npz');q=z['points_mm'];t=z['triangles'];world=q*.001;inverse=np.linalg.inv(worlds[ni]);assert np.linalg.det(worlds[ni][:3,:3])>0
        local=world@inverse[:3,:3].T+inverse[:3,3];flat=local[t].reshape(-1,3).astype(np.float32)
        reopened=(flat.astype(float)@worlds[ni][:3,:3].T+worlds[ni][:3,3])*1000;target=reopened.reshape(-1,3,3)
        p=original[ni].reshape(-1,3);old_t=np.arange(len(p)).reshape(-1,3)
        # Independently seeded face probes in addition to original fine samples.
        sp=np.concatenate([samples(original[ni]),scan.area_samples(original[ni],40000,seed=417)])
        tp=np.concatenate([samples(target),scan.area_samples(target,40000,seed=419)])
        fwd=distances(sp,reopened,np.arange(len(reopened)).reshape(-1,3));rev=distances(tp,p,old_t)
        maximum=max(float(fwd.max()),float(rev.max()));top=topology(reopened,np.arange(len(reopened)).reshape(-1,3));before=row['topology_before']
        compatible=all(before[k]==top[k]for k in ['components','euler','boundary_edges'])and top['nonmanifold_edges']<=before['nonmanifold_edges']
        qualified=maximum<=1 and compatible
        rec={k:row[k]for k in ['node','component','before_triangles','after_triangles','placed_saving']}
        rec.update(reopened_forward_max_mm=float(fwd.max()),reopened_reverse_max_mm=float(rev.max()),topology=top,
            source_probes=len(fwd),candidate_probes=len(rev),qualifies_after_reopen=qualified)
        records.append(rec)
        if not qualified:continue
        mesh=doc['meshes'][doc['nodes'][ni]['mesh']];assert len(mesh['primitives'])==1;old=mesh['primitives'][0];assert set(old['attributes'])=={'POSITION','NORMAL'}
        g=flat.reshape(-1,3,3).astype(float);normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
        pr=copy.deepcopy(old);pr['attributes']={
            'POSITION':append_accessor(candidate,binary,flat,'VEC3',5126),
            'NORMAL':append_accessor(candidate,binary,np.repeat(normal,3,axis=0).astype(np.float32),'VEC3',5126)}
        pr['indices']=append_accessor(candidate,binary,np.arange(len(flat),dtype=np.uint32),'SCALAR',5125)
        newmesh=copy.deepcopy(mesh);newmesh['primitives']=[pr];candidate['nodes'][ni]['mesh']=len(candidate['meshes']);candidate['meshes'].append(newmesh);changed.add(ni)
    target=OUT/'rune-collision-plates-trial.glb';write_glb(target,candidate,compact(candidate,binary));new,nb=read_glb(target)
    exact=0;assert doc['scenes']==new['scenes'];assert doc['materials']==new['materials'];assert doc['asset']==new['asset']
    for ni,(before,after)in enumerate(zip(doc['nodes'],new['nodes'])):
        assert {k:v for k,v in before.items()if k!='mesh'}=={k:v for k,v in after.items()if k!='mesh'}
        if 'mesh'not in before or ni in changed:continue
        pp=doc['meshes'][before['mesh']]['primitives'];qq=new['meshes'][after['mesh']]['primitives'];assert len(pp)==len(qq)
        for p,q in zip(pp,qq):
            assert {k:v for k,v in p.items()if k not in ['attributes','indices']}=={k:v for k,v in q.items()if k not in ['attributes','indices']}
            assert p['attributes'].keys()==q['attributes'].keys()
            for key in p['attributes']:
                a=accessor(doc,blob,p['attributes'][key]);b=accessor(new,nb,q['attributes'][key]);assert a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()
            assert np.array_equal(accessor(doc,blob,p['indices']),accessor(new,nb,q['indices']))
        exact+=1
    saving=scene_triangles(doc)-scene_triangles(new);assert saving==sum(r['placed_saving']for r in records if r['qualifies_after_reopen'])
    for p,h in json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text())['pins'].items():assert scan.digest(Path(p))==h
    assert scan.digest(baseline)==stage['assets']['rune']['sha256']
    report=dict(baseline=str(baseline),baseline_sha256=scan.digest(baseline),reviewed_checkpoint=str(stage_path),
        reviewed_checkpoint_sha256=scan.digest(stage_path),candidate=str(target),candidate_sha256=scan.digest(target),
        baseline_triangles=scene_triangles(doc),candidate_triangles=scene_triangles(new),placed_saving=saving,
        qualified_nodes=sorted(changed),records=records,unchanged_mesh_owners_exact=exact,
        metadata_ancestry_transforms_materials_exact=True,visuals_unchanged=True,installed=False,contact_approved=False,
        combined_field_if_adopted=stage['placed_mesh_triangles']-saving,
        limitations='Finite bidirectional surface checks plus topology invariants. No continuous, contact-normal, all-pose or runtime speed certificate. This new trial is not part of the committed accepted checkpoint.')
    (OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Reopened qualified',len(changed),'plates;',saving,'placed triangles saved;',scene_triangles(doc),'->',scene_triangles(new),';',exact,'other mesh owners exact.')
    for r in records:print(r['node'],round(max(r['reopened_forward_max_mm'],r['reopened_reverse_max_mm']),6),r['qualifies_after_reopen'])


if __name__=='__main__':main()
