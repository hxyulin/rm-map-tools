"""Uninstalled Outpost mesh trial: retain covered convex exterior, drop interiors."""
import copy,importlib.util,json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('closed_export_adaptive',Path(__file__).with_name('adaptive.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
from gltf_scene import read_glb,write_glb,scene_nodes,accessor
from simplify_package import append_accessor,compact,scene_triangles
OUT=a.OUT


def main():
    rows=json.loads((OUT/'closed-envelope-coverage.json').read_text());source=Path(rows[0]['source'])
    assert a.original.digest(source)==rows[0]['source_sha256']
    d,b=read_glb(source);n=copy.deepcopy(d);binary=bytearray(b);worlds={i:w for i,w,_ in scene_nodes(d)};changed={r['node']for r in rows};proofs=[]
    for row in rows:
        ni=row['node'];c=row['coverage'];assert c['all_facets_covered_with_tolerance']and c['all_facets_outward_facing_covered']
        p=np.asarray(c['native_hull_vertices_mm'])/1000;h=ConvexHull(p);t=h.simplices.copy()
        normal=np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]])
        flip=np.einsum('ij,ij->i',normal,h.equations[:,:3])<0;t[flip]=t[flip][:,[0,2,1]]
        w=worlds[ni];assert np.linalg.det(w[:3,:3])>0;inv=np.linalg.inv(w)
        local=p@inv[:3,:3].T+inv[:3,3];flat=local[t].reshape(-1,3).astype(np.float32)
        g=flat.reshape(-1,3,3).astype(float);normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
        mesh=d['meshes'][d['nodes'][ni]['mesh']];assert len(mesh['primitives'])==1;old=mesh['primitives'][0]
        primitive=copy.deepcopy(old);primitive['attributes']={
            'POSITION':append_accessor(n,binary,flat,'VEC3',5126),
            'NORMAL':append_accessor(n,binary,np.repeat(normal,3,axis=0).astype(np.float32),'VEC3',5126)}
        primitive['indices']=append_accessor(n,binary,np.arange(len(flat),dtype=np.uint32),'SCALAR',5125)
        newmesh=copy.deepcopy(mesh);newmesh['primitives']=[primitive]
        n['nodes'][ni]['mesh']=len(n['meshes']);n['meshes'].append(newmesh)
        proofs.append(dict(node=ni,source_triangles=c['source_triangles'],new_triangles=len(t),
            interior_triangles_omitted=c['interior_or_nonplanar_triangles'],
            outward_exterior_coverage=True,raw_uncovered_area_mm2=c['raw_uncovered_area_mm2']))
    path=OUT/'outpost-collision-closed-envelope-trial.glb';write_glb(path,n,compact(n,binary));dd,bb=read_glb(path)
    exact=0
    assert d['asset']==dd['asset'];assert d['scenes']==dd['scenes'];assert d['materials']==dd['materials']
    for i,(before,after)in enumerate(zip(d['nodes'],dd['nodes'])):
        assert {k:v for k,v in before.items()if k!='mesh'}=={k:v for k,v in after.items()if k!='mesh'}
        if 'mesh'not in before or i in changed:continue
        x=d['meshes'][before['mesh']]['primitives'];y=dd['meshes'][after['mesh']]['primitives'];assert len(x)==len(y)
        for old,new in zip(x,y):
            assert {k:v for k,v in old.items()if k not in ['attributes','indices']}=={k:v for k,v in new.items()if k not in ['attributes','indices']}
            assert old['attributes'].keys()==new['attributes'].keys()
            for key in old['attributes']:
                p=accessor(d,b,old['attributes'][key]);q=accessor(dd,bb,new['attributes'][key]);assert p.shape==q.shape and p.dtype==q.dtype and p.tobytes()==q.tobytes()
            assert np.array_equal(accessor(d,b,old['indices']),accessor(dd,bb,new['indices']))
        exact+=1
    _,_,newgroups=a.original.load_nodes(path)
    from mesh_quality import distances
    roundtrip=[]
    for row in rows:
        p=np.asarray(row['coverage']['native_hull_vertices_mm']);g=p[ConvexHull(p).simplices];q=newgroups[row['node']]
        probes=a.base.probes(g,4000);reverse=a.base.probes(q,4000)
        error=max(distances(probes,q.reshape(-1,3),np.arange(q.size//3).reshape(-1,3)).max(),
            distances(reverse,g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3)).max())
        roundtrip.append(dict(node=row['node'],hull_roundtrip_sampled_max_mm=float(error)))
    before,after=scene_triangles(d),scene_triangles(dd);assert before-after==552
    for p,h in json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text())['pins'].items():assert a.original.digest(Path(p))==h
    proof=dict(source=str(source),source_sha256=rows[0]['source_sha256'],candidate=str(path),candidate_sha256=a.original.digest(path),
        source_triangles_per_asset=before,candidate_triangles_per_asset=after,placed_mesh_savings=2*(before-after),
        placed_native_alternative_mesh_triangles_replaced=2*sum(r['coverage']['source_triangles']for r in rows),
        source_geometry_unchanged_outside_nodes=sorted(changed),unchanged_mesh_owners_exact=exact,
        node_metadata_transforms_ancestry_materials_exact=True,coverage=proofs,float32_roundtrip=roundtrip,
        installed=False,contact_approved=False,native_shapes=False,
        limitation='Closed exterior geometrically covered by outward source facets. Removing interior faces changes inside-origin queries; current physics/query/motion behavior and package integration not tested. This file is a triangle-mesh preview only.')
    (OUT/'outpost-export-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(before,after,'placed saving',2*(before-after),'unchanged',exact,'roundtrip',roundtrip)


if __name__=='__main__':main()
