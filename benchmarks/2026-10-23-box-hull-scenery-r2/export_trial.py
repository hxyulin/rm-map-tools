"""Build an uninstalled triangle-mesh trial, replacing six selected islands.

All other source primitive payloads and every node/material/scene are retained.
This is a mesh collision preview, not a native primitive sidecar.
"""
import copy
import importlib.util
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('adaptive_scenery_export',Path(__file__).with_name('adaptive.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
from gltf_scene import read_glb,write_glb,scene_nodes,accessor,mesh_instances
from simplify_package import append_accessor,compact,scene_triangles
OUT=a.OUT


def main():
    rows=json.loads((OUT/'adaptive.json').read_text());screen=json.loads((OUT/'screen.json').read_text())
    source=Path(screen['source']);assert a.original.digest(source)==screen['source_sha256']
    doc,blob=read_glb(source);candidate=copy.deepcopy(doc);binary=bytearray(blob)
    worlds={ni:w for ni,w,_ in scene_nodes(doc)};records=[]
    for ni in [354,587]:
        chosen=[r for r in rows if r['node']==ni and r['source_triangles']in[482,484]
                and r['proof']['inward_envelope_limit_mm']==.5]
        assert len(chosen)==3
        removed=np.concatenate([r['source_triangle_indices']for r in chosen]);assert len(removed)==len(set(removed))
        mesh=doc['meshes'][doc['nodes'][ni]['mesh']];assert len(mesh['primitives'])==1
        old=mesh['primitives'][0];indices=accessor(doc,blob,old['indices']).reshape(-1,3)
        keep=np.ones(len(indices),bool);keep[removed]=False
        retained=copy.deepcopy(old);retained['indices']=append_accessor(candidate,binary,indices[keep].reshape(-1),'SCALAR',doc['accessors'][old['indices']]['componentType'])
        primitives=[retained];w=worlds[ni];inverse=np.linalg.inv(w)
        assert np.linalg.det(w[:3,:3])>0
        for row in chosen:
            p=np.asarray(row['hull_vertices_mm'])/1000;h=ConvexHull(p);t=h.simplices.copy()
            n=np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]])
            bad=np.einsum('ij,ij->i',n,h.equations[:,:3])<0;t[bad]=t[bad][:,[0,2,1]]
            local=p@inverse[:3,:3].T+inverse[:3,3];flat=local[t].reshape(-1,3).astype(np.float32)
            triangles=flat.reshape(-1,3,3).astype(float);normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
            new=dict(mode=4,material=old['material'],attributes={
                'POSITION':append_accessor(candidate,binary,flat,'VEC3',5126),
                'NORMAL':append_accessor(candidate,binary,np.repeat(normal,3,axis=0).astype(np.float32),'VEC3',5126)},
                indices=append_accessor(candidate,binary,np.arange(len(flat),dtype=np.uint32),'SCALAR',5125))
            primitives.append(new)
        replacement=copy.deepcopy(mesh);replacement['primitives']=primitives
        candidate['nodes'][ni]['mesh']=len(candidate['meshes']);candidate['meshes'].append(replacement)
        records.append(dict(node=ni,retained_source_triangles=int(keep.sum()),
            removed_source_triangles=len(removed),added_hull_triangles=sum(r['preview_triangles']for r in chosen),
            source_triangle_indices=removed.tolist(),islands=[r['island']for r in chosen]))
    target=OUT/'arena-static-collision-trial.glb'
    write_glb(target,candidate,compact(candidate,binary));new,nb=read_glb(target)
    assert doc['materials']==new['materials'];assert doc['scenes']==new['scenes'];assert doc['asset']==new['asset']
    changed={354,587};unchanged=0
    for ni,(n,nn)in enumerate(zip(doc['nodes'],new['nodes'])):
        assert {k:v for k,v in n.items()if k!='mesh'}=={k:v for k,v in nn.items()if k!='mesh'}
        if 'mesh'not in n:continue
        pp=doc['meshes'][n['mesh']]['primitives'];qq=new['meshes'][nn['mesh']]['primitives']
        if ni not in changed:assert len(pp)==len(qq)
        for old,pr in zip(pp,qq):
            assert old.get('material')==pr.get('material')
            assert set(old['attributes'])==set(pr['attributes'])
            for key in old['attributes']:
                x=accessor(doc,blob,old['attributes'][key]);y=accessor(new,nb,pr['attributes'][key]);assert x.dtype==y.dtype and x.shape==y.shape and x.tobytes()==y.tobytes()
            x=accessor(doc,blob,old['indices']).reshape(-1,3);y=accessor(new,nb,pr['indices']).reshape(-1,3)
            if ni in changed:
                row=next(r for r in records if r['node']==ni);mask=np.ones(len(x),bool);mask[row['source_triangle_indices']]=False;x=x[mask]
            assert x.dtype==y.dtype and np.array_equal(x,y)
        if ni not in changed:unchanged+=1
    before=scene_triangles(doc);after=scene_triangles(new);assert before-after==2648
    # Reopen source-world candidate geometry to verify the float32 round trip.
    expected={}
    for ni in changed:
        selected=[r for r in rows if r['node']==ni and r['source_triangles']in[482,484]and r['proof']['inward_envelope_limit_mm']==.5]
        expected[ni]=[np.asarray(r['hull_vertices_mm'])for r in selected]
    max_roundtrip=0.
    for ni,pi,p,t,mat in mesh_instances(new,nb):
        if ni not in changed or pi==0:continue
        q=expected[ni][pi-1]
        from scipy.spatial import cKDTree
        d,_=cKDTree(q).query(p*1000);max_roundtrip=max(max_roundtrip,float(d.max()))
    for path,sha in json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text())['pins'].items():assert a.original.digest(Path(path))==sha
    proof=dict(source=str(source),source_sha256=screen['source_sha256'],target=str(target),
        target_sha256=a.original.digest(target),records=records,before_triangles=before,after_triangles=after,
        placed_mesh_triangle_saving=before-after,unchanged_mesh_owners_exact=unchanged,
        node_metadata_transforms_ancestry_exact=True,materials_scenes_asset_exact=True,
        retained_source_arrays_exact=True,maximum_hull_vertex_roundtrip_mm=max_roundtrip,
        contact_approved=False,installed=False,native_shapes=False,
        review_status='conditional-strand-gap-fill-low-priority',
        caveat='Six triangulated compact hulls replace three-strand bundles, filling the spaces between strands. This is deliberate local detail coarsening, not a main-frame simplification. Physics contact/motion/ground queries remain unvalidated.')
    (OUT/'export-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(before,after,before-after,'triangles saved;',unchanged,'unchanged owners exact; max vertex roundtrip mm',max_roundtrip)


if __name__=='__main__':main()
