"""Freeze the user-reviewed R2 geometry without changing installed assets.

Git retains scripts, selectors and hashes; derived CAD meshes stay under out/.
Native hull representation remains a separate alternative to mesh fallback.
"""
import copy
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
spec=importlib.util.spec_from_file_location('checkpoint_scan',ROOT/'benchmarks/2026-10-23-box-primitive-candidates/scan.py')
scan=importlib.util.module_from_spec(spec);spec.loader.exec_module(scan)
from gltf_scene import read_glb,write_glb,accessor
from simplify_package import append_accessor,compact,scene_triangles
OUT=ROOT/'out/rmuc2027-collision-review-checkpoint'
RULE=ROOT/'rules/collision-review-checkpoint-rmuc2027.json'


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def export_rune():
    rows=json.loads((ROOT/'out/rmuc2027-box-hull-rune-r2/shortlist.json').read_text())['candidates']
    source=Path(rows[0]['source']);assert digest(source)==rows[0]['source_sha256']
    doc,blob=read_glb(source);candidate=copy.deepcopy(doc);binary=bytearray(blob)
    _,_,groups=scan.load_nodes(source);changed={121,122,123};proof=[]
    for row in rows:
        ni=row['node'];assert ni in changed
        ids=np.asarray(row['selector']['triangle_indices'],dtype='<i8')
        assert hashlib.sha256(ids.tobytes()).hexdigest()==row['selector']['triangle_indices_sha256']
        assert hashlib.sha256(groups[ni][ids].astype('<f8').tobytes()).hexdigest()==row['selector']['selected_triangle_coordinates_float64_mm_sha256']
        mesh=doc['meshes'][doc['nodes'][ni]['mesh']];assert len(mesh['primitives'])==1;old=mesh['primitives'][0]
        idx=accessor(doc,blob,old['indices']).reshape(-1,3);keep=np.ones(len(idx),bool);keep[ids]=False;primitives=[]
        if keep.any():
            retained=copy.deepcopy(old);retained['indices']=append_accessor(candidate,binary,idx[keep].ravel(),'SCALAR',doc['accessors'][old['indices']]['componentType']);primitives.append(retained)
        points=np.asarray(row['native_hull_owner_local_vertices_metres']);h=ConvexHull(points);t=h.simplices.copy()
        cr=np.cross(points[t[:,1]]-points[t[:,0]],points[t[:,2]]-points[t[:,0]])
        flip=np.einsum('ij,ij->i',cr,h.equations[:,:3])<0;t[flip]=t[flip][:,[0,2,1]]
        flat=points[t].reshape(-1,3).astype(np.float32);g=flat.reshape(-1,3,3).astype(float)
        normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
        hull=copy.deepcopy(old);hull['attributes']={
            'POSITION':append_accessor(candidate,binary,flat,'VEC3',5126),
            'NORMAL':append_accessor(candidate,binary,np.repeat(normal,3,axis=0).astype(np.float32),'VEC3',5126)}
        hull['indices']=append_accessor(candidate,binary,np.arange(len(flat),dtype=np.uint32),'SCALAR',5125)
        primitives.append(hull);replacement=copy.deepcopy(mesh);replacement['primitives']=primitives
        candidate['nodes'][ni]['mesh']=len(candidate['meshes']);candidate['meshes'].append(replacement)
        proof.append(dict(node=ni,selected_triangles=len(ids),retained_triangles=int(keep.sum()),hull_triangles=len(t),
            selector_sha256=row['selector']['triangle_indices_sha256']))
    target=OUT/'collision/rune.glb';target.parent.mkdir(parents=True,exist_ok=True)
    write_glb(target,candidate,compact(candidate,binary));after,ab=read_glb(target)
    assert scene_triangles(doc)-scene_triangles(after)==1436
    exact=0
    assert doc['materials']==after['materials'];assert doc['scenes']==after['scenes'];assert doc['asset']==after['asset']
    for ni,(old,new)in enumerate(zip(doc['nodes'],after['nodes'])):
        assert {k:v for k,v in old.items()if k!='mesh'}=={k:v for k,v in new.items()if k!='mesh'}
        if 'mesh'not in old:continue
        pp=doc['meshes'][old['mesh']]['primitives'];qq=after['meshes'][new['mesh']]['primitives']
        if ni in changed:
            row=next(x for x in rows if x['node']==ni)
            if row['retained_attached_island_triangles']:
                oldpr=pp[0];newpr=qq[0]
                for key in oldpr['attributes']:assert np.array_equal(accessor(doc,blob,oldpr['attributes'][key]),accessor(after,ab,newpr['attributes'][key]))
                ids=row['selector']['triangle_indices'];idx=accessor(doc,blob,oldpr['indices']).reshape(-1,3);mask=np.ones(len(idx),bool);mask[ids]=False
                assert np.array_equal(idx[mask],accessor(after,ab,newpr['indices']).reshape(-1,3))
            continue
        assert len(pp)==len(qq)
        for x,y in zip(pp,qq):
            assert {k:v for k,v in x.items()if k not in ['attributes','indices']}=={k:v for k,v in y.items()if k not in ['attributes','indices']}
            assert x['attributes'].keys()==y['attributes'].keys()
            for key in x['attributes']:
                a=accessor(doc,blob,x['attributes'][key]);b=accessor(after,ab,y['attributes'][key]);assert a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()
            assert np.array_equal(accessor(doc,blob,x['indices']),accessor(after,ab,y['indices']))
        exact+=1
    return dict(source=str(source),source_sha256=digest(source),candidate=str(target),candidate_sha256=digest(target),
        before=scene_triangles(doc),after=scene_triangles(after),placed_saving=1436,unchanged_mesh_owners_exact=exact,
        unchanged_node_metadata_materials_ancestry=True,records=proof)


def build():
    OUT.mkdir(exist_ok=True);ref=json.loads(scan.REF.read_text());rune=export_rune()
    exports=json.loads((ROOT/'out/rmuc2027-box-hull-scenery-r2/export-verification.json').read_text())
    outpost=json.loads((ROOT/'out/rmuc2027-box-hull-scenery-r2/outpost-export-verification.json').read_text())
    overrides={'rune':Path(rune['candidate']),'arena-static':Path(exports['target']),'outpost':Path(outpost['candidate'])}
    expected={'arena-static':exports['target_sha256'],'outpost':outpost['candidate_sha256'],'rune':rune['candidate_sha256']}
    assets={};visual={};total=0
    for asset,row in ref['roles']['collision']['assets'].items():
        source=Path(row['path']);assert digest(source)==row['sha256']
        selected=overrides.get(asset,source)
        if asset in expected:assert digest(selected)==expected[asset]
        target=OUT/'collision'/f'{asset}.glb';target.parent.mkdir(parents=True,exist_ok=True)
        if target!=selected:shutil.copyfile(selected,target)
        d,_=read_glb(target);count=scene_triangles(d);placed=count*row['placements'];total+=placed
        assets[asset]=dict(path=str(target),sha256=digest(target),source_sha256=row['sha256'],triangles=count,
            placements=row['placements'],placed_triangles=placed)
        vr=ref['roles']['visual']['assets'][asset];assert digest(vr['path'])==vr['sha256'];visual[asset]=dict(path=vr['path'],sha256=vr['sha256'])
    assert total==540411
    stage=dict(schema='rm-map-tools.reviewed-collision-checkpoint-1',id='reviewed-box-hull-rmuc2027-r2',
        review_status='user accepted displayed approximations and requested commit',
        installed=False,contact_validated=False,reference=str(scan.REF),assets=assets,visual_reference=visual,
        placed_mesh_triangles=total,source_placed_mesh_triangles=545599,placed_mesh_saving=5188,
        native_alternative=dict(mesh_remainder_triangles=538279,native_hull_leaves=23,
            replaces_source_mesh_triangles=7320,field_import_implemented=False,
            note='Alternative to mesh fallback, not an additional saving. Core exact hulls have zero mesh-fallback saving.'))
    (OUT/'stage.json').write_text(json.dumps(stage,indent=2)+'\n')
    (OUT/'rune-verification.json').write_text(json.dumps(rune,indent=2)+'\n')
    freeze(stage)
    print('Reviewed checkpoint:',total,'placed mesh triangles;',545599-total,'saved; visuals unchanged; installed assets unchanged.')


def freeze(stage):
    def pin(rel):p=ROOT/rel;return dict(path=rel,sha256=digest(p))
    manifests=[pin('out/rmuc2027-box-hull-equipment-r2/shortlist.json'),pin('out/rmuc2027-box-hull-rune-r2/shortlist.json'),
        pin('out/rmuc2027-box-hull-scenery-r2/adaptive.json'),pin('out/rmuc2027-box-hull-scenery-r2/closed-envelope-coverage.json')]
    rule=dict(schema_version=1,id=stage['id'],reference='rules/manual-review-reference-rmuc2027.json',
        user_approval='User accepted the displayed R2 approximations and requested commit; no runtime installation requested.',
        selected_families=[dict(asset='outpost',nodes=[26,28,30],operation='closed-exterior hull; remove covered interior faces'),
            dict(asset='tech-core',nodes=[53,54,55,56],island=0,operation='exact convex native alternative; retain mesh fallback unchanged'),
            dict(asset='rune',nodes=[121,122,123],island=0,operation='convex hull of selected support plates; fill reviewed fastener slots; retain other islands'),
            dict(asset='arena-static',node_islands={'354':[5,6,16],'587':[116,147,148]},operation='0.5mm inscribed envelope hull; reviewed strand-gap filling')],
        rejected=['whole Energy-unit hulls','whole resource-mechanism hulls','Core288 uncovered exterior','unreviewed whole-frame/enclosure hulls'],
        evidence=manifests,mesh_checkpoint=dict(stage_path='out/rmuc2027-collision-review-checkpoint/stage.json',
            stage_sha256=digest(OUT/'stage.json'),placed_triangles=540411,placed_saving=5188,
            assets={k:{q:r[q]for q in ['sha256','source_sha256','triangles','placements','placed_triangles']}for k,r in stage['assets'].items()}),
        native_alternative=stage['native_alternative'],installed=False,contact_validated=False,
        reproduction='ocpenv/bin/python -B benchmarks/2026-10-23-collision-review-checkpoint/checkpoint.py --build',
        storage='CAD-derived GLBs and detailed geometry ledgers stay under ignored out/. Git records tooling, hashes and selection policy.')
    if '--freeze' in sys.argv:RULE.write_text(json.dumps(rule,indent=2)+'\n')
    elif RULE.exists():
        old=json.loads(RULE.read_text());assert old==rule,'checkpoint changed; inspect before explicitly freezing a new rule'


def verify():
    rule=json.loads(RULE.read_text());stage=json.loads((OUT/'stage.json').read_text())
    assert digest(OUT/'stage.json')==rule['mesh_checkpoint']['stage_sha256']
    for evidence in rule['evidence']:assert digest(ROOT/evidence['path'])==evidence['sha256']
    for asset,row in stage['assets'].items():
        assert digest(row['path'])==row['sha256'];d,_=read_glb(row['path']);assert scene_triangles(d)==row['triangles']
        assert row['sha256']==rule['mesh_checkpoint']['assets'][asset]['sha256']
    for row in stage['visual_reference'].values():assert digest(row['path'])==row['sha256']
    for path,sha in json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text())['pins'].items():assert digest(path)==sha
    assert sum(r['placed_triangles']for r in stage['assets'].values())==540411
    print('Verified reviewed rule, evidence hashes, six collision outputs, six unchanged visuals and all installed pins.')


if __name__=='__main__':
    if '--build' in sys.argv:build()
    if '--verify' in sys.argv or '--build'not in sys.argv:verify()
