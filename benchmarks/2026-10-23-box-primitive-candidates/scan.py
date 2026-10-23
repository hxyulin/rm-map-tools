"""Screen installed rigid mesh occurrences for boxes and compact convex hulls.

Only investigation artifacts are written. Distances are finite samples, never
contact approval. Frames are source active-scene coordinates in millimetres.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, QhullError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, mesh_instances, scene_nodes
from mesh_quality import distances

OUT = ROOT / 'out/rmuc2027-box-primitive-candidates'
REF = ROOT / 'out/rmuc2027-installed-reference-review/review.json'
FACES = np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
                  [2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def area_samples(g, count, seed=123):
    cross = np.cross(g[:,1]-g[:,0], g[:,2]-g[:,0])
    area = np.linalg.norm(cross, axis=1)
    rng = np.random.default_rng(seed)
    ids = rng.choice(len(g), count, p=area/area.sum())
    a = rng.random(count) ** .5
    b = rng.random(count)
    return ((1-a)[:,None]*g[ids,0] + (a*(1-b))[:,None]*g[ids,1]
            + (a*b)[:,None]*g[ids,2])


def frames(g):
    p = g.reshape(-1,3)
    _, _, vt = np.linalg.svd(p-p.mean(0), full_matrices=False)
    choices = [np.eye(3), vt.T]
    n = np.cross(g[:,1]-g[:,0], g[:,2]-g[:,0])
    area = np.linalg.norm(n, axis=1)
    n = n / np.maximum(area[:,None], 1e-30)
    # Dominant surface normals, weighted by area rather than CAD tessellation.
    sign = np.sign(n[np.arange(len(n)), np.argmax(abs(n),axis=1)])
    n *= sign[:,None]
    key, inverse = np.unique(np.round(n,2), axis=0, return_inverse=True)
    weights = np.bincount(inverse, weights=area)
    normals = []
    for idx in np.argsort(weights)[-6:][::-1]:
        v = np.sum(n[inverse==idx]*area[inverse==idx,None], axis=0)
        if np.linalg.norm(v)<1e-12: continue
        v /= np.linalg.norm(v)
        normals.append(v)
    for x in normals[:3]:
        orth = sorted(normals, key=lambda n: abs(n@x))
        y = orth[0] - (orth[0]@x)*x
        if np.linalg.norm(y)<.1: continue
        y /= np.linalg.norm(y)
        choices.append(np.column_stack((x,y,np.cross(x,y))))
    for f in choices:
        if np.linalg.det(f)<0: f[:,2]*=-1
        yield f


def sdf_box(p, center, frame, half):
    q = abs((p-center)@frame)-half
    return np.linalg.norm(np.maximum(q,0),axis=1)+np.minimum(q.max(1),0)


def box_points(center, frame, half):
    return np.array([[x,y,z] for x in [-half[0],half[0]]
                     for y in [-half[1],half[1]] for z in [-half[2],half[2]]])@frame.T+center


def box_grid(center, frame, half, step, maximum=160000):
    grids = []
    for axis in range(3):
        a,b = [i for i in range(3) if i!=axis]
        na,nb = np.maximum(2,np.ceil(2*half[[a,b]]/step).astype(int)+1)
        if 2*na*nb + sum(len(x) for x in grids)>maximum:
            return None
        aa,bb = np.meshgrid(np.linspace(-half[a],half[a],na),
                            np.linspace(-half[b],half[b],nb))
        for level in [-half[axis],half[axis]]:
            q = np.zeros((aa.size,3)); q[:,axis]=level
            q[:,a]=aa.ravel(); q[:,b]=bb.ravel()
            grids.append(q@frame.T+center)
    return np.concatenate(grids)


def fit_boxes(g):
    p = np.unique(g.reshape(-1,3),axis=0)
    s = area_samples(g,4096)
    result=[]
    for f in frames(g):
        local=p@f
        # Strict extrema and trimmed area proposals are evaluated independently.
        for mode in ['enclosing','area-trimmed-0.25pct']:
            lo,hi = (local.min(0),local.max(0)) if mode=='enclosing' else np.quantile(s@f,[.0025,.9975],axis=0)
            h=(hi-lo)/2
            if h.min()<.05: continue
            c=((hi+lo)/2)@f.T
            error=sdf_box(p,c,f,h)
            sampled=sdf_box(s,c,f,h)
            outside=float(np.maximum(error,0).max())
            surface=float(abs(error).max())
            # Broad phase is only a shortlist, with all source vertices checked.
            score=max(outside,float(np.quantile(abs(sampled),.99)))
            result.append(dict(mode=mode,center_mm=c.tolist(),axes_columns=f.tolist(),
                half_extents_mm=h.tolist(),source_outside_max_mm=outside,
                source_surface_max_mm=surface,area_p99_surface_mm=float(np.quantile(abs(sampled),.99)),
                area_fraction_surface_over_1mm=float(np.mean(abs(sampled)>1)),
                area_fraction_outside_over_1mm=float(np.mean(sampled>1)),score=score))
    return sorted(result,key=lambda x:x['score'])


def load_nodes(path):
    doc,blob=read_glb(path)
    groups={}; components={}
    for ni,world,parent in scene_nodes(doc):
        components[ni]=doc['nodes'][ni].get('extras',{}).get('component_id',components.get(parent,''))
    for ni,pi,p,t,mat in mesh_instances(doc,blob):
        groups.setdefault(ni,[]).append(p[t]*1000)
    return doc,components,{ni:np.concatenate(parts) for ni,parts in groups.items()}


def run():
    OUT.mkdir(exist_ok=True)
    ref=json.loads(REF.read_text()); rows=[]; pins={}; counts={}
    for asset,info in ref['roles']['collision']['assets'].items():
        path=Path(info['path']); assert digest(path)==info['sha256']; pins[str(path)]=digest(path)
        doc,components,nodes=load_nodes(path); counts[asset]=len(nodes)
        for ni,g in nodes.items():
            if len(g)<100 or np.ptp(g.reshape(-1,3),axis=0).max()<20: continue
            candidates=fit_boxes(g)
            if not candidates: continue
            row=dict(asset=asset,node=ni,name=doc['nodes'][ni].get('name'),
                component=components[ni],source_triangles=len(g),placements=info['placements'],
                placed_triangles=len(g)*info['placements'],source=str(path),
                source_sha256=info['sha256'],box_proposals=candidates[:3])
            rows.append(row)
        print(asset,len(nodes),'mesh nodes; screen rows',len(rows),flush=True)
    (OUT/'screen.json').write_text(json.dumps(dict(pins=pins,mesh_nodes=counts,rows=rows),indent=2)+'\n')
    verify(rows,pins,counts)


def verify(rows,pins,counts):
    cache={}; verified=[]; hulls=[]
    # Dense reverse checks only for promising preliminary fits.
    shortlisted=sorted([r for r in rows if r['box_proposals'][0]['score']<=6],key=lambda r:-r['placed_triangles'])
    for row in shortlisted:
        path=Path(row['source'])
        if str(path) not in cache: cache[str(path)]=load_nodes(path)[2]
        g=cache[str(path)][row['node']]; p=g.reshape(-1,3); t=np.arange(len(p)).reshape(-1,3)
        trials=[]
        for fit in row['box_proposals']:
            if fit['score']>6: continue
            c,f,h=map(np.asarray,[fit['center_mm'],fit['axes_columns'],fit['half_extents_mm']])
            grid=box_grid(c,f,h,3)
            if grid is None:
                trials.append({**fit,'status':'reverse-grid-budget-exceeded'}); continue
            reverse=distances(grid,p,t)
            error=max(fit['source_surface_max_mm'],float(reverse.max()))
            trial={**fit,'reverse_max_mm':float(reverse.max()),'reverse_sample_count':len(grid),
                'symmetric_sampled_max_mm':error,'max_mm_over_longest_span':error/(2*h.max()),
                'preview_triangles':12,'native_parts':1,
                'placed_mesh_triangles_replaced':row['placed_triangles'],
                'status':'sampled-within-3mm' if error<=3 else ('sampled-within-5mm' if error<=5 else 'not-qualified'),
                'solid_fill_review': max(fit['source_outside_max_mm'],float(reverse.max()))<=3,
                'note':'Interior source-to-box distances include intentionally filled bores; solid_fill_review is not contact approval.'}
            trials.append(trial)
        if trials:
            best=min(trials,key=lambda x:x.get('symmetric_sampled_max_mm',1e12))
            verified.append({**row,'box_proposals':trials,'best':best})
            print('reverse',row['asset'],row['node'],row['placed_triangles'],best.get('symmetric_sampled_max_mm'),flush=True)
    # Compact convex envelopes, never arbitrary large assemblies.
    for row in sorted(rows,key=lambda r:-r['placed_triangles'])[:90]:
        path=Path(row['source'])
        if str(path) not in cache: cache[str(path)]=load_nodes(path)[2]
        g=cache[str(path)][row['node']]; p=np.unique(g.reshape(-1,3),axis=0)
        try: hull=ConvexHull(p)
        except QhullError: continue
        if len(hull.simplices)>=min(256,len(g)//2): continue
        surface=area_samples(p[hull.simplices],4096)
        reverse=distances(np.concatenate([p[hull.vertices],surface]),g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3))
        hulls.append({k:v for k,v in row.items() if k!='box_proposals'} | dict(
            hull_vertices=len(hull.vertices),hull_facets=len(hull.simplices),
            reverse_sampled_max_mm=float(reverse.max()),reverse_samples=len(reverse),
            source_outside_mm=0.,note='Exact convex envelope of all source vertices; fills every concavity. Reverse sampling only, no contact approval.'))
    for path,sha in pins.items(): assert digest(Path(path))==sha
    result=dict(reference=str(REF),pins=pins,mesh_nodes=counts,screened_nodes=len(rows),
                reverse_checked_nodes=len(verified),boxes=verified,convex_hulls=hulls,
                limitations='No continuous distance bound, pose/sweep/contact certification, selection adoption, native export or runtime change. Source and installed assets unchanged. Dense reverse box grid uses 3mm pitch; finite samples can miss features.')
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('complete',len(verified),'boxes',len(hulls),'hulls',flush=True)


if __name__=='__main__':
    run()
