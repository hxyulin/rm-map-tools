# SPDX-License-Identifier: MIT OR Apache-2.0
"""Explicit lossy compact detail omission from accepted refined 1 mm GLBs."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_component_detail import connected_pieces
from gltf_scene import accessor, read_glb, scene_nodes, write_glb
from mesh_quality import distances
from simplify_package import append_accessor, compact, protected, scene_triangles

OUT = ROOT / 'out/rmuc2027-detail-trial'
BASE = ROOT / 'out/rmuc2027-runtime-opportunities/refined'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def optical(doc, prim):
    mat = doc['materials'][prim.get('material', 0)]
    rgb = mat.get('extras', {}).get('step_colour_srgb')
    if rgb is None:
        rgb = mat.get('pbrMetallicRoughness', {}).get('baseColorFactor', [.5,.5,.5,1])[:3]
    return bool(set(prim['attributes']) - {'POSITION', 'NORMAL'} or
                np.ptp(rgb) >= .15 or max(mat.get('emissiveFactor', [0,0,0])) > 0 or
                protected(prim.get('extras', {}).get('rm', {})) or
                any('Texture' in k for k in mat) or
                any('Texture' in k for k in mat.get('pbrMetallicRoughness', {})))


def counts(doc, placements):
    active = {doc['nodes'][i]['mesh'] for i,_,_ in scene_nodes(doc) if 'mesh' in doc['nodes'][i]}
    stored = sum(doc['accessors'][p.get('indices', p['attributes']['POSITION'])]['count']//3
                 for i in active for p in doc['meshes'][i]['primitives'])
    scene = scene_triangles(doc)
    return {'stored_triangles': stored, 'scene_triangles': scene, 'placed_triangles': scene * placements,
            'active_mesh_definitions':len(active)}


def prepare(doc, blob):
    rows = []
    boxes = []
    scopes, inherited = {}, {}
    for i,w,parent in scene_nodes(doc):
        n=doc['nodes'][i]; ex=n.get('extras',{});rm=ex.get('rm',{})
        own = ex.get('component_id') or rm.get('part_id') or rm.get('id')
        scopes[i] = i if own else scopes.get(parent,i)
        inherited[i] = inherited.get(parent,False) or protected(rm)
        if 'mesh' not in n: continue
        prims = doc['meshes'][n['mesh']]['primitives']
        geometry=[]; metas=[]
        for pi,pr in enumerate(prims):
            p=accessor(doc,blob,pr['attributes']['POSITION'])
            t=(accessor(doc,blob,pr['indices']) if 'indices' in pr else np.arange(len(p))).reshape(-1,3)
            g=(p.astype(float) @ w[:3,:3].T + w[:3,3])[t]*1000
            guard=bool(inherited[i] or optical(doc,pr))
            if guard: boxes.append((g.min((0,1)),g.max((0,1))))
            geometry.append(g);metas.append((pi, len(t), guard))
        g=np.concatenate(geometry)
        # Connectivity is tested across primitive/material seams within this node.
        labels=connected_pieces(g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3))
        rows.append({'node':i,'scope':scopes[i],'g':g,'labels':labels,'meta':metas})
    return rows, np.asarray(boxes)


def choose(row, boxes, size):
    g=row['g'];labels=row['labels'];guard=np.concatenate([np.full(n,prot) for _,n,prot in row['meta']])
    records=[];eligible=[]
    for label in np.unique(labels):
        ids=np.flatnonzero(labels==label);part=g[ids];lo=part.min((0,1));hi=part.max((0,1));span=hi-lo
        near=False
        if len(boxes):
            delta=np.maximum(np.maximum(boxes[:,0]-hi,lo-boxes[:,1]),0)
            near=bool((np.linalg.norm(delta,axis=1)<=8).any())
        reason='eligible'
        if guard[ids].any():reason='protected-appearance-or-semantic'
        elif near:reason='conservative-8mm-optical-box-neighborhood'
        elif span.max()>=size:reason='extent-limit'
        r={'piece':int(label),'triangles':len(ids),'bounds_mm':[lo.tolist(),hi.tolist()],
           'span_mm':span.tolist(),'reason':reason,'removed':False}
        records.append(r)
        if reason=='eligible':eligible.append(label)
    candidate=np.isin(labels,eligible)
    backing=g[~candidate].reshape(-1,3)
    keep=np.ones(len(g),bool)
    if len(backing) and candidate.any():
        points,inv=np.unique(g[candidate].reshape(-1,3),axis=0,return_inverse=True)
        errors=distances(points,backing,np.arange(len(backing)).reshape(-1,3))
        trierror=np.zeros(len(g));trierror[candidate]=errors[inv].reshape(-1,3).max(1)
        for r in records:
            if r['reason']!='eligible':continue
            ids=np.flatnonzero(labels==r['piece']);e=float(trierror[ids].max());r['maximum_vertex_backing_distance_mm']=e
            if e<size:
                keep[ids]=False;r['removed']=True;r['reason']='explicit-lossy-size-and-backing-omission'
            else:r['reason']='backing-limit'
    else:
        for r in records:
            if r['reason']=='eligible':r['reason']='no-retained-backing'
    # Dense deterministic deletion-only deviation against retained geometry.
    removed=g[~keep]
    deviation=None
    if len(removed):
        samples=[]
        for a in range(5):
            for b in range(5-a):
                samples.append((a*removed[:,0]+b*removed[:,1]+(4-a-b)*removed[:,2])/4)
        sample=np.concatenate(samples)
        retained=g[keep].reshape(-1,3)
        error=distances(sample,retained,np.arange(len(retained)).reshape(-1,3))
        # Every omitted point lies in a <= sqrt(3)*size bounding box. This loose
        # bound is separate from the dense sampled measurement.
        deviation={'samples':len(sample),'omitted_to_retained_max_mm':float(error.max()),
                   'omitted_to_retained_p99_mm':float(np.percentile(error,99)),
                   'retained_to_input_mm':0.0,'loose_surface_upper_bound_mm':float(size*(1+np.sqrt(3))),
                   'method':'15 barycentric samples per omitted triangle; not Hausdorff certification'}
    return keep,records,deviation


def trial(source, target, size, placements, rows, boxes, origin_groups):
    start=time.perf_counter();doc,blob=read_glb(source);changed=copy.deepcopy(doc);binary=bytearray(blob)
    ledger=[];selections={};mesh_cache={}
    for row in rows:
        keep,parts,dev=choose(row,boxes,size)
        if keep.all():continue
        i=row['node'];old=doc['nodes'][i]['mesh'];newpr=[];offset=0;selection=[]
        for pi,n,guard in row['meta']:
            pr=doc['meshes'][old]['primitives'][pi];ids=np.flatnonzero(keep[offset:offset+n]);offset+=n
            selection.append(ids.tolist())
            if not len(ids):continue
            cp=copy.deepcopy(pr)
            if len(ids)!=n:
                t=(accessor(doc,blob,pr['indices']) if 'indices' in pr else np.arange(doc['accessors'][pr['attributes']['POSITION']]['count'])).reshape(-1,3)
                cp['indices']=append_accessor(changed,binary,np.ascontiguousarray(t[ids].ravel(),dtype=np.uint32),'SCALAR',5125)
            newpr.append(cp)
        assert newpr, 'never omit whole mesh owner'
        key=(old,json.dumps(selection))
        if key not in mesh_cache:
            mesh_cache[key]=len(changed['meshes']);changed['meshes'].append({**copy.deepcopy(doc['meshes'][old]),'primitives':newpr})
        changed['nodes'][i]['mesh']=mesh_cache[key]
        selections[i]=selection
        ex=doc['nodes'][i].get('extras',{})
        origins=[{k:v for k,v in r.items() if k!='panels'} for r in origin_groups if r['scope_node']==row['scope']]
        ledger.append({'node':i,'name':doc['nodes'][i].get('name'),'scope_node':row['scope'],
                       'scope_metadata':doc['nodes'][row['scope']].get('extras',{}),'source_owner':ex,
                       'refined_source_owner_pools':origins,
                       'before_triangles':len(keep),'after_triangles':int(keep.sum()),
                       'retained_triangle_indices_by_baseline_primitive':selection,
                       'parts':parts,'deviation':dev})
    if not ledger:return None
    changed['asset'].setdefault('extras',{}).update(inspection_only=True,collision_approved=False,
           compact_detail_trial={'extent_and_vertex_backing_mm':size,'optical_neighborhood_mm':8,'explicitly_lossy':True})
    payload=compact(changed,binary);target.parent.mkdir(parents=True,exist_ok=True);write_glb(target,changed,payload)
    actual,ab=read_glb(target)
    assert len(actual['nodes'])==len(doc['nodes'])
    assert actual['materials']==doc['materials']
    for i,w,pa in scene_nodes(doc):
        n=doc['nodes'][i];an=actual['nodes'][i]
        assert {k:v for k,v in n.items() if k!='mesh'}=={k:v for k,v in an.items() if k!='mesh'}
        if 'mesh' not in n:continue
        spr=doc['meshes'][n['mesh']]['primitives'];apr=actual['meshes'][an['mesh']]['primitives'];slot=0
        for pi,pr in enumerate(spr):
            t=(accessor(doc,blob,pr['indices']) if 'indices' in pr else np.arange(doc['accessors'][pr['attributes']['POSITION']]['count'])).reshape(-1,3)
            ids=np.asarray(selections[i][pi],dtype=int) if i in selections else np.arange(len(t))
            if not len(ids):continue
            ap=apr[slot];slot+=1
            assert pr.get('material')==ap.get('material')
            assert {k:v for k,v in pr.items() if k not in ('indices','attributes')}=={k:v for k,v in ap.items() if k not in ('indices','attributes')}
            for name,ai in pr['attributes'].items():assert np.array_equal(accessor(doc,blob,ai),accessor(actual,ab,ap['attributes'][name]))
            assert np.array_equal(t[ids].ravel(),accessor(actual,ab,ap['indices']))
        assert slot==len(apr)
    # Embedded image bytes survive compaction independently of view indices.
    for before,after in zip(doc.get('images',[]),actual.get('images',[])):
        if 'bufferView' in before:
            bv=doc['bufferViews'][before['bufferView']];av=actual['bufferViews'][after['bufferView']]
            assert blob[bv.get('byteOffset',0):bv.get('byteOffset',0)+bv['byteLength']]==ab[av.get('byteOffset',0):av.get('byteOffset',0)+av['byteLength']]
    return {'input':str(source.resolve()),'input_sha256':digest(source),'output':str(target.resolve()),
            'output_sha256':digest(target),'extent_mm_strict':size,'vertex_backing_mm_strict':size,
            'optical_neighborhood_mm':8,'backing_scope':'same baseline mesh node; no other component/part/joint used',
            'before':counts(doc,placements),'after':counts(actual,placements),'nodes':ledger,
            'verification':'reopened; exact retained triangle indices and all original attribute arrays; original node indices, metadata, ancestry, transforms; materials and embedded image bytes',
            'processing_seconds':time.perf_counter()-start}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    refined=json.loads((BASE.parent/'refined.json').read_text())
    report={'inputs':{},'candidate_map':{},'policies':{'conservative-8mm':8,'aggressive-17mm':17},'assets':[],
            'limitations':['Explicitly lossy deletion, never hidden/containment proof.',
            'Can erase neutral compact fasteners, caps, spacers, chips and socket/gripper manufacturing detail outside protected neighborhoods; unclassified small functional details may be lost.',
            'Active mechanisms are never selected wholesale: each changed node retains larger/protected backing, and all original ownership nodes remain.',
            'Original pre-refinement triangle identity is unavailable for reconstructed batches: owner pools are recorded, exact selection references accepted refined input.',
            'No runtime installation, collision approval or performance claim.']}
    manifests=[]
    for rel in ['manifest.json','equipment/manifest.json']:
        path=ROOT.parent/'rm-simulator/field-2027'/rel
        manifests.append((path,json.loads(path.read_text())))
    for _,manifest in manifests:
        for name,asset in manifest['assets'].items():
            for role in ['visual','collision']:
                source=BASE/(role+'-1mm')/asset[role]
                doc,blob=read_glb(source);rows,boxes=prepare(doc,blob)
                report['inputs'][str(source.resolve())]={'sha256':digest(source),'asset':name,'role':role,
                   'placements':max(1,len(asset['placements_in_source_arena_frame'])),
                   'counts':counts(doc,max(1,len(asset['placements_in_source_arena_frame'])))}
                for policy,size in report['policies'].items():
                    target=OUT/policy/(role+'-1mm')/source.name
                    r=trial(source,target,size,max(1,len(asset['placements_in_source_arena_frame'])),rows,boxes,refined['assets'][name+'/'+role]['groups'])
                    if r:
                        r.update(asset=name,role=role,policy=policy);report['assets'].append(r)
                        report['candidate_map'].setdefault(policy,{})[str(source.resolve())]={'output':str(target.resolve()),'role':role,'asset':name}
                        print(policy,name,role,r['before']['placed_triangles'],'->',r['after']['placed_triangles'],flush=True)
                    else:print(policy,name,role,'unchanged',flush=True)
    for source,metadata in report['inputs'].items():assert digest(Path(source))==metadata['sha256'], 'input changed'
    report['totals']={}
    for policy in report['policies']:
        totals={}
        for role in ['visual','collision']:
            before=sum(r['counts']['placed_triangles'] for r in report['inputs'].values() if r['role']==role)
            saved=sum(r['before']['placed_triangles']-r['after']['placed_triangles'] for r in report['assets'] if r['policy']==policy and r['role']==role)
            totals[role]={'before_placed_triangles':before,'after_placed_triangles':before-saved,'saved_placed_triangles':saved}
        report['totals'][policy]=totals
    report['producer_sha256']=digest(Path(__file__))
    (OUT/'ledger.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
