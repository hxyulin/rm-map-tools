# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent coarse housing review; crucial top geometry is protected.

Selections refer to the pinned, already reviewed 17 mm detail candidate. They
are manual review decisions, not inferred gameplay or containment semantics.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

from audit import detail, OUT, ROOT
import meshoptimizer as mo
import numpy as np
from scipy.spatial import ConvexHull
from gltf_scene import accessor, read_glb, scene_nodes, write_glb
from simplify_package import append_accessor, compact, scene_triangles
from mesh_quality import distances
from cad_collision_profiles import mesh_metrics


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def samples(g):
    return np.concatenate([(a*g[:,0]+b*g[:,1]+(4-a-b)*g[:,2])/4
                           for a in range(5) for b in range(5-a)])


def measure(old, new):
    forward = distances(samples(old),new.reshape(-1,3),np.arange(new.size//3).reshape(-1,3))
    reverse = distances(samples(new),old.reshape(-1,3),np.arange(old.size//3).reshape(-1,3))
    return {'forward_max_mm':float(forward.max()),'reverse_max_mm':float(reverse.max()),
            'samples':len(forward)+len(reverse),'method':'15 barycentric points per triangle, both directions; not a continuous certificate'}


def hull_housing(g):
    p=np.unique(g.reshape(-1,3),axis=0);h=ConvexHull(p);t=h.simplices.copy()
    normal=np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]])
    flip=np.einsum('ij,ij->i',normal,h.equations[:,:3])<0;t[flip]=t[flip][:,::-1]
    ix=np.ascontiguousarray(t.ravel(),dtype=np.uint32);q=np.ascontiguousarray(p-p.mean(0),dtype=np.float32);dest=np.empty_like(ix)
    count=mo.simplify(dest,ix,q,target_index_count=96*3,target_error=3,options=mo.SIMPLIFY_ERROR_ABSOLUTE)
    result=p[dest[:count].reshape(-1,3)]
    qp,qi=np.unique(np.round(result.reshape(-1,3),5),axis=0,return_inverse=True)
    topology=mesh_metrics(qp,qi.reshape(-1,3))
    assert topology['closed_oriented_manifold']
    # This deliberate cap/undercut closure is separate from outer-hull faceting.
    return result,{'hull_triangles':len(t),'target_triangles':96,'hull_simplifier_error_mm':3,
                   'topology':topology,
                   'faceting_vs_unsimplified_hull':measure(p[t],result),
                   'deliberate_loss':'Fills the selected housing bores and concave interior/recess surfaces; no 1 mm surface-equivalence claim.'}


def export(role, policy):
    source=ROOT/f'out/rmuc2027-detail-trial/aggressive-17mm/{role}-1mm'/('tech-core'+('-collision' if role=='collision' else '')+'.glb')
    pinned={'visual':'94ccded671598882dcc7bf33d229810c486d3c845bd315b9f28ca446fa1f1181',
            'collision':'7a7ee312ea201b016825b628eed5ef33baea69a417662889c1bd756f87fae9da'}
    assert digest(source)==pinned[role], 'reviewed baseline changed'
    doc,blob=read_glb(source);rows,_=detail.prepare(doc,blob);changed=copy.deepcopy(doc);binary=bytearray(blob)
    worlds={i:w for i,w,_ in scene_nodes(doc)};records=[]
    # User correction: the entire tool head, including its crucial top geometry,
    # is protected. Only the independent arm-housing experiment may change.
    housings={1672:[1,3,4,15,19,24]}
    for row in rows:
        node=row['node'];selected=[]
        if policy in ('housings','combined'):selected += housings.get(node,[])
        if not selected:continue
        mesh=doc['meshes'][doc['nodes'][node]['mesh']];offset=0;prim_ids=np.zeros(len(row['g']),int);guard=np.zeros(len(row['g']),bool)
        for pi,n,gd in row['meta']:prim_ids[offset:offset+n]=pi;guard[offset:offset+n]=gd;offset+=n
        removed=np.zeros(len(row['g']),bool);additions=[]
        batches=[[label]for label in selected]
        for labels in batches:
            ids=np.flatnonzero(np.isin(row['labels'],labels));g=row['g'][ids]
            assert len(ids) and not guard[ids].any() and len(np.unique(prim_ids[ids]))==1
            pi=int(prim_ids[ids[0]]);primitive=mesh['primitives'][pi]
            assert set(primitive['attributes'])<= {'POSITION','NORMAL'}
            out,operation=hull_housing(g);kind='coarse-outer-housing'
            if len(out)>=len(g):continue
            removed[ids]=True
            additions.append((out,primitive))
            records.append({'node':node,'pieces':labels,'operation':kind,'material':primitive['material'],
                            'before_triangles':len(g),'after_triangles':len(out),'details':operation,
                            'deviation_vs_reviewed_component':measure(g,out)})
        if not removed.any():continue
        newpr=[];offset=0
        for pi,n,_ in row['meta']:
            pr=mesh['primitives'][pi];keep=~removed[offset:offset+n];offset+=n
            if not keep.any():continue
            cp=copy.deepcopy(pr)
            if not keep.all():
                t=accessor(doc,blob,pr['indices']).reshape(-1,3)
                cp['indices']=append_accessor(changed,binary,np.ascontiguousarray(t[keep].ravel(),dtype=np.uint32),'SCALAR',5125)
            newpr.append(cp)
        inverse=np.linalg.inv(worlds[node])
        for out,pr in additions:
            # Replace only this node's independently selected surface pieces.
            local=(out/1000-worlds[node][:3,3])@inverse[:3,:3].T
            p=local.reshape(-1,3).astype(np.float32);normal=np.cross(local[:,1]-local[:,0],local[:,2]-local[:,0]);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-20)
            normals=np.repeat(normal,3,axis=0).astype(np.float32);cp=copy.deepcopy(pr)
            cp['attributes']={'POSITION':append_accessor(changed,binary,p,'VEC3',5126),
                              'NORMAL':append_accessor(changed,binary,normals,'VEC3',5126)}
            cp['indices']=append_accessor(changed,binary,np.arange(len(p),dtype=np.uint32),'SCALAR',5125)
            newpr.append(cp)
        if newpr:
            changed['nodes'][node]['mesh']=len(changed['meshes']);changed['meshes'].append({**copy.deepcopy(mesh),'primitives':newpr})
        else:changed['nodes'][node].pop('mesh')
    target=OUT/policy/source.name;target.parent.mkdir(parents=True,exist_ok=True)
    if not records:
        import shutil
        shutil.copyfile(source,target)
        return {'role':role,'policy':policy,'source':str(source),'source_sha256':pinned[role],
                'output':str(target),'output_sha256':digest(target),'before_per_core':scene_triangles(doc),
                'after_per_core':scene_triangles(doc),'placed_saved_triangles':0,'selections':[],
                'status':'restored-exact-reviewed-baseline'}
    changed['asset'].setdefault('extras',{}).update(inspection_only=True,collision_approved=False,
                                                  manual_tech_core_trial=policy)
    payload=compact(changed,binary);write_glb(target,changed,payload)
    actual,ab=read_glb(target)
    assert actual['materials']==doc['materials']
    assert len(actual['nodes'])==len(doc['nodes'])
    for a,b in zip(doc['nodes'],actual['nodes']):assert {k:v for k,v in a.items()if k!='mesh'}=={k:v for k,v in b.items()if k!='mesh'}
    for i,w,pa in scene_nodes(actual):
        n=actual['nodes'][i]
        if 'mesh' not in n:continue
        for pr in actual['meshes'][n['mesh']]['primitives']:
            p=accessor(actual,ab,pr['attributes']['POSITION']);ix=accessor(actual,ab,pr['indices'])
            assert np.isfinite(p).all() and len(ix)%3==0 and ix.max()<len(p)
            for ai in pr['attributes'].values():assert np.isfinite(accessor(actual,ab,ai)).all()
    before=scene_triangles(doc);after=scene_triangles(actual)
    assert before-after==sum(r['before_triangles']-r['after_triangles'] for r in records)
    assert digest(source)==pinned[role]
    return {'role':role,'policy':policy,'source':str(source),'source_sha256':pinned[role],
            'output':str(target),'output_sha256':digest(target),'before_per_core':before,'after_per_core':after,
            'placed_saved_triangles':2*(before-after),'selections':records}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    for role,policy in [('visual','vents'),('collision','vents'),('visual','housings'),('visual','combined')]:
        r=export(role,policy);results.append(r)
        print(role,policy,r['before_per_core'],'->',r['after_per_core'],'placed saved',r['placed_saved_triangles'],flush=True)
    (OUT/'ledger.json').write_text(json.dumps({'trials':results,'scope':'Manual selections on reviewed 17 mm baseline; uninstalled inspection candidates. Top geometry restored exactly at user request; vent/shield replacements and associated deletions withdrawn. Only the independent visual arm-housing experiment remains.'},indent=2)+'\n')


if __name__=='__main__':main()
