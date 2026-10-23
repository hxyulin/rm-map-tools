"""Simplify convex envelopes with a measured maximum inward displacement.

The envelope approximation is measured at EVERY original hull vertex using
Euclidean triangle distance. Convexity bounds envelope loss throughout the
original hull. This does NOT certify cavity fills or physical contacts.
"""
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull,QhullError

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('scenery_r2_scan',Path(__file__).with_name('scan.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
original=base.original;OUT=base.OUT;distances=base.distances


def reduced_hull(points,tol):
    full=ConvexHull(points);outer=points[full.vertices]
    _,_,vt=np.linalg.svd(outer-outer.mean(0),full_matrices=False)
    golden=np.pi*(3-np.sqrt(5));z=np.linspace(-.98,.98,24);angle=np.arange(24)*golden
    directions=np.column_stack([np.sqrt(1-z*z)*np.cos(angle),np.sqrt(1-z*z)*np.sin(angle),z])@vt
    chosen=set(np.argmax(outer@directions.T,axis=0).tolist())
    history=[]
    for _ in range(len(outer)):
        q=outer[sorted(chosen)];h=ConvexHull(q)
        error=distances(outer,q,h.simplices)
        worst=int(np.argmax(error));maximum=float(error[worst]);history.append(maximum)
        if maximum<=tol+1e-9:
            return q[h.vertices],dict(original_hull_vertices=len(outer),retained_vertices=len(h.vertices),
                maximum_original_hull_vertex_distance_mm=maximum,iterations=len(history),
                inward_envelope_limit_mm=tol)
        if worst in chosen:raise ValueError('adaptive hull stopped making progress')
        chosen.add(worst)
    raise ValueError('could not reproduce original hull')


def main():
    screen=json.loads((OUT/'screen.json').read_text());source=Path(screen['source'])
    assert original.digest(source)==screen['source_sha256']
    doc,components,nodes=original.load_nodes(source)
    inventory=screen['rows'];selected=[]
    for row in inventory:
        # New dense rounded/sculpted members and prior frame island comparisons.
        if row['component'] in ['energy-unit/unit','resource-area/mechanism'] or (
                row['node'] in [354,587] and row['source_triangles'] in [482,484]):
            selected.append(row)
    results=[]
    for row in selected:
        g=nodes[row['node']][row['source_triangle_indices']];p=np.unique(g.reshape(-1,3),axis=0)
        for tol in [.5,1.0]:
            try:q,proof=reduced_hull(p,tol)
            except QhullError:continue
            hull=ConvexHull(q);cg=q[hull.simplices]
            fw=distances(base.probes(g,40000),q,hull.simplices)
            rv=base.reverse(g,cg,False)
            # All source vertices outside the new envelope are measured exactly.
            signed=p@hull.equations[:,:3].T+hull.equations[:,3]
            outside=signed.max(1)>1e-7
            outward=distances(p[outside],q,hull.simplices) if outside.any() else np.array([0.])
            result={**{k:v for k,v in row.items()if k!='trials'},'kind':'adaptive-hull',
                'hull_vertices_mm':q.tolist(),'proof':proof,'preview_triangles':len(cg),
                'mesh_triangle_saving':len(g)-len(cg),'native_parts':1,
                'native_mesh_triangles_replaced':len(g),'forward_max_mm':float(fw.max()),
                'forward_samples':len(fw),'source_vertex_outside_max_mm':float(outward.max()),
                'reverse':rv,'strict_sampled_max_mm':max(float(fw.max()),rv['max_mm']),
                'caveat':'The envelope loss limit does not bound filled holes/concavities or contact normals. All source vertices, including interior faces, are separately included in forward surface checks.',
                'contact_approved':False}
            results.append(result)
            print(row['node'],row['island'],len(g),tol,len(cg),'fwd',round(float(fw.max()),3),'rev',round(rv['max_mm'],3),flush=True)
    assert original.digest(source)==screen['source_sha256']
    (OUT/'adaptive.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':main()
