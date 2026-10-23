"""Find source-owner-local box/hull opportunities in scenery mesh islands.

No geometric welding, owner merging or source changes. Finite surface checks
qualify investigation candidates, not physical contacts or installed assets.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import ConvexHull, QhullError

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-box-primitive-candidates'))
import scan as original
# This file deliberately uses a distinct import name when imported by report.py.
from mesh_quality import distances
from gltf_scene import scene_nodes
OUT=ROOT/'out/rmuc2027-box-hull-scenery-r2'


def islands(g):
    p,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True)
    t=inv.reshape(-1,3);e=np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]])
    n,labels=connected_components(coo_matrix((np.ones(len(e)),(e[:,0],e[:,1])),shape=(len(p),len(p))),directed=False)
    return labels[t[:,0]],n


def probes(g, count=4096):
    return np.concatenate([np.unique(g.reshape(-1,3),axis=0),g.mean(1),
        (g[:,0]+g[:,1])/2,(g[:,1]+g[:,2])/2,(g[:,2]+g[:,0])/2,
        original.area_samples(g,count,seed=439)])


def source_topology(g):
    p,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);t=inv.reshape(-1,3)
    e=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1)
    _,c=np.unique(e,axis=0,return_counts=True)
    return dict(vertices=len(p),boundary_edges=int(sum(c==1)),nonmanifold_edges=int(sum(c>2)))


def reverse(g,candidate,coarse=True):
    p=g.reshape(-1,3);t=np.arange(len(p)).reshape(-1,3)
    x=probes(candidate,1536 if coarse else 40000)
    d=distances(x,p,t)
    return dict(max_mm=float(d.max()),p99_mm=float(np.quantile(d,.99)),samples=len(x))


def run():
    OUT.mkdir(exist_ok=True)
    ref=json.loads(original.REF.read_text());info=ref['roles']['collision']['assets']['arena-static']
    source=Path(info['path']);assert original.digest(source)==info['sha256']
    doc,components,nodes=original.load_nodes(source);worlds={i:(w,p)for i,w,p in scene_nodes(doc)}
    counts=dict(mesh_nodes=len(nodes),dense_mesh_nodes=0,exact_islands=0,eligible_islands=0)
    inventory=[]
    for ni,g in nodes.items():
        if len(g)<64 or ni in [260,493]:continue
        counts['dense_mesh_nodes']+=1;labels,n=islands(g);counts['exact_islands']+=n
        for label in np.unique(labels):
            ids=np.flatnonzero(labels==label)
            if len(ids)<64:continue
            selected=g[ids];span=np.sort(np.ptp(selected.reshape(-1,3),axis=0))
            if span[-1]<100 or span[-2]<20:continue
            inventory.append(dict(node=ni,island=int(label),source_triangles=len(ids),
                component=components[ni],name=doc['nodes'][ni].get('name'),
                source_triangle_indices=ids.tolist(),selector_sha256=hashlib.sha256(ids.astype('<i8').tobytes()).hexdigest()))
    inventory.sort(key=lambda r:-r['source_triangles']);counts['eligible_islands']=len(inventory)
    rows=[]
    # Bounded by source density, not cherry-picked prior fit results.
    for row in inventory[:450]:
        g=nodes[row['node']][row['source_triangle_indices']];p=np.unique(g.reshape(-1,3),axis=0)
        fit=original.fit_boxes(g)
        trials=[]
        for b in fit[:3]:
            if b['source_surface_max_mm']>5:continue
            c,f,h=map(np.asarray,[b['center_mm'],b['axes_columns'],b['half_extents_mm']])
            q=original.box_points(c,f,h);cg=q[original.FACES]
            rv=reverse(g,cg)
            fw=abs(original.sdf_box(probes(g,1024),c,f,h))
            trials.append(dict(kind='box',center_mm=c.tolist(),axes_columns=f.tolist(),half_extents_mm=h.tolist(),
                preview_triangles=len(cg),native_vertices=8,forward_max_mm=float(fw.max()),
                reverse=rv,strict_max_mm=max(float(fw.max()),rv['max_mm'])))
        try:
            hull=ConvexHull(p)
            if len(hull.simplices)<min(512,len(g)*.75):
                cg=p[hull.simplices]
                rv=reverse(g,cg)
                if rv['max_mm']<=12:
                    fw=distances(probes(g,1024),p,hull.simplices)
                    trials.append(dict(kind='hull',hull_vertices_mm=p[hull.vertices].tolist(),
                        preview_triangles=len(cg),native_vertices=len(hull.vertices),
                        forward_max_mm=float(fw.max()),reverse=rv,
                        strict_max_mm=max(float(fw.max()),rv['max_mm'])))
        except QhullError:pass
        ancestry=[];ancestor=row['node']
        while ancestor is not None:
            ancestry.append(dict(index=ancestor,name=doc['nodes'][ancestor].get('name'),extras=doc['nodes'][ancestor].get('extras',{})))
            ancestor=worlds[ancestor][1]
        rows.append({**row,'source':str(source),'source_sha256':info['sha256'],
            'node_world_matrix':worlds[row['node']][0].tolist(),'ancestry_root_first':ancestry[::-1],
            'trials':sorted(trials,key=lambda x:x['strict_max_mm']),
            'bounds_mm':[p.min(0).tolist(),p.max(0).tolist()],
            'source_topology':source_topology(g)})
        if trials:
            best=min(trials,key=lambda x:x['strict_max_mm'])
            print(row['node'],row['island'],len(g),best['kind'],round(best['strict_max_mm'],4),flush=True)
    assert original.digest(source)==info['sha256']
    (OUT/'screen.json').write_text(json.dumps(dict(source=str(source),source_sha256=info['sha256'],counts=counts,
        scanned_islands=len(rows),inventory=inventory,rows=rows,
        limitations='Exact vertex-connected islands are not certified solid bodies. Finite samples, no adoption. Excludes previously reviewed whole plates260/493. Native ground/scenery importer currently does not accept arena-static shape recipes.'),indent=2)+'\n')
    refine(rows,nodes)


def refine(rows,nodes):
    candidates=[]
    for row in rows:
        if not row['trials']:continue
        g=nodes[row['node']][row['source_triangle_indices']]
        longest=float(np.ptp(g.reshape(-1,3),axis=0).max())
        for trial in row['trials']:
            if trial['strict_max_mm']>5 or trial['strict_max_mm']/longest>.035:continue
            if trial['kind']=='box':
                c,f,h=map(np.asarray,[trial['center_mm'],trial['axes_columns'],trial['half_extents_mm']])
                cg=original.box_points(c,f,h)[original.FACES]
                grid=original.box_grid(c,f,h,1.,maximum=220000)
                if grid is None:continue
                rv=distances(np.concatenate([grid,original.area_samples(cg,40000,seed=811)]),
                    g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3))
                fw=abs(original.sdf_box(probes(g,40000),c,f,h))
                reverse_info=dict(max_mm=float(rv.max()),p99_mm=float(np.quantile(rv,.99)),samples=len(rv),box_grid_pitch_mm=1.)
            else:
                p=np.asarray(trial['hull_vertices_mm']);hull=ConvexHull(p);cg=p[hull.simplices]
                fw=distances(probes(g,40000),p,hull.simplices)
                reverse_info=reverse(g,cg,False)
            strict=max(float(fw.max()),reverse_info['max_mm'])
            candidates.append({**{k:v for k,v in row.items()if k!='trials'},'shape':trial,
                'forward_max_mm':float(fw.max()),'forward_samples':len(fw),'reverse':reverse_info,
                'strict_sampled_max_mm':strict,'max_fraction_longest_world_axis_span':strict/longest,
                'preview_triangles':len(cg),'mesh_triangle_saving':row['source_triangles']-len(cg),
                'native_parts':1,'native_mesh_triangles_replaced':row['source_triangles'],
                'status':'sampled-within-3mm' if strict<=3 else ('sampled-within-5mm' if strict<=5 else 'rejected-after-dense-check'),
                'contact_approved':False})
    assert all(original.digest(Path(r['source']))==r['source_sha256'] for r in candidates)
    (OUT/'candidates.json').write_text(json.dumps(candidates,indent=2)+'\n')
    print('REFINED',len(candidates),flush=True)


if __name__=='__main__':run()
