"""Distinguish buried faces from missing exterior on three Outpost members.

Coverage is checked geometrically on every hull facet, rather than inferring a
solid exterior from sparse reverse samples. This does not test internal rays,
motion placement or solver contacts.
"""
import importlib.util,json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull,QhullError
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('adaptive_closed_envelopes',Path(__file__).with_name('adaptive.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
OUT=a.OUT


def coverage(g,eps=.001):
    p=np.unique(g.reshape(-1,3),axis=0);h=ConvexHull(p)
    cr=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);areas=np.linalg.norm(cr,axis=1)/2
    exterior=np.zeros(len(g),bool);facet_records=[]
    for k,(tri,equation) in enumerate(zip(h.simplices,h.equations)):
        normal=equation[:3];level=equation[3]
        coplanar=np.max(abs(g@normal+level),axis=1)<=eps
        exterior|=coplanar
        q=p[tri];origin=q[0];u=q[1]-q[0];u/=np.linalg.norm(u);v=np.cross(normal,u);f=np.column_stack([u,v])
        face=Polygon((q-origin)@f)
        projected=(g[coplanar]-origin)@f
        polys=[Polygon(t)for t in projected]
        polys=[t for t in polys if t.is_valid and t.area>1e-10]
        covered=unary_union(polys)if polys else Polygon()
        winding=np.einsum('ij,j->i',cr[coplanar],normal)>0
        outward_polys=[Polygon(t)for t,ok in zip(projected,winding)if ok]
        outward_polys=[t for t in outward_polys if t.is_valid and t.area>1e-10]
        outward_covered=unary_union(outward_polys)if outward_polys else Polygon()
        raw_missing=float(face.difference(covered).area)
        missing=float(face.difference(covered.buffer(eps)).area)
        outward_missing=float(face.difference(outward_covered.buffer(eps)).area)
        facet_records.append(dict(facet=k,source_coplanar_triangles=int(sum(coplanar)),
            hull_facet_area_mm2=float(face.area),raw_uncovered_area_mm2=raw_missing,
            uncovered_area_after_tolerance_buffer_mm2=missing,
            outward_facing_uncovered_area_mm2=outward_missing))
    return dict(source_triangles=len(g),hull_vertices=len(h.vertices),hull_preview_triangles=len(h.simplices),
        source_triangles_on_hull_boundary=int(sum(exterior)),interior_or_nonplanar_triangles=int(sum(~exterior)),
        interior_or_nonplanar_area_mm2=float(areas[~exterior].sum()),
        hull_area_mm2=float(h.area),raw_uncovered_area_mm2=sum(x['raw_uncovered_area_mm2']for x in facet_records),
        uncovered_area_after_tolerance_buffer_mm2=sum(x['uncovered_area_after_tolerance_buffer_mm2']for x in facet_records),
        geometric_tolerance_mm=eps,all_facets_covered_with_tolerance=all(x['uncovered_area_after_tolerance_buffer_mm2']<1e-6 for x in facet_records),
        all_facets_outward_facing_covered=all(x['outward_facing_uncovered_area_mm2']<1e-6 for x in facet_records),
        facet_coverage=facet_records,exterior_triangle_indices=np.flatnonzero(exterior).tolist(),
        interior_or_nonplanar_triangle_indices=np.flatnonzero(~exterior).tolist(),
        native_hull_vertices_mm=p[h.vertices].tolist())


def main():
    ref=json.loads(a.original.REF.read_text());info=ref['roles']['collision']['assets']['outpost'];source=Path(info['path'])
    assert a.original.digest(source)==info['sha256'];doc,components,nodes=a.original.load_nodes(source);rows=[]
    for ni in [26,28,30]:
        result=coverage(nodes[ni]);rows.append(dict(asset='outpost',node=ni,name=doc['nodes'][ni].get('name'),
            component=components[ni],source=str(source),source_sha256=info['sha256'],placements=info['placements'],
            coverage=result,source_world_bounds_mm=[nodes[ni].min((0,1)).tolist(),nodes[ni].max((0,1)).tolist()],
            contact_approved=False,
            interpretation='Coverage of the closed convex outer envelope is checked per facet. Removing the strictly interior source faces changes queries from inside and needs explicit ownership/contact review. This is not approval from a low all-surface error.'))
        print(ni,result['source_triangles'],result['hull_preview_triangles'],result['source_triangles_on_hull_boundary'],result['interior_or_nonplanar_triangles'],result['raw_uncovered_area_mm2'],result['uncovered_area_after_tolerance_buffer_mm2'],flush=True)
    assert a.original.digest(source)==info['sha256']
    (OUT/'closed-envelope-coverage.json').write_text(json.dumps(rows,indent=2)+'\n')


def global_scan():
    ref=json.loads(a.original.REF.read_text());inventory=[];shortlist=[];pins={};checked=0;coarse=0
    for asset,info in ref['roles']['collision']['assets'].items():
        source=Path(info['path']);assert a.original.digest(source)==info['sha256'];pins[str(source)]=info['sha256']
        doc,components,nodes=a.original.load_nodes(source)
        for ni,g in nodes.items():
            if len(g)<100:continue
            p=np.unique(g.reshape(-1,3),axis=0)
            try:h=ConvexHull(p)
            except QhullError:continue
            if len(h.simplices)>=min(128,len(g)*.75):continue
            checked+=1
            probes=np.concatenate([p[h.vertices],a.original.area_samples(p[h.simplices],512,seed=901)])
            distance=a.distances(probes,g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3))
            row=dict(asset=asset,node=ni,name=doc['nodes'][ni].get('name'),component=components[ni],source=str(source),
                source_sha256=info['sha256'],source_triangles=len(g),placements=info['placements'],
                hull_preview_triangles=len(h.simplices),coarse_reverse_max_mm=float(distance.max()))
            if distance.max()<.01:
                coarse+=1;proof=coverage(g);row['coverage']=proof
                if proof['all_facets_covered_with_tolerance']:
                    shortlist.append({**row,'placed_mesh_saving':(len(g)-len(h.simplices))*info['placements'],
                        'native_hull_leaves':info['placements'],'native_mesh_triangles_replaced':len(g)*info['placements'],
                        'status':'closed-envelope-review' if proof['all_facets_outward_facing_covered'] else 'coverage-only-winding-review',
                        'contact_approved':False})
            inventory.append(row)
        print('global',asset,'screened',checked,'coarse-near-exact',coarse,'coverage-passed',len(shortlist),flush=True)
    for p,sha in pins.items():assert a.original.digest(Path(p))==sha
    (OUT/'closed-envelope-global.json').write_text(json.dumps(dict(pins=pins,screened=checked,
        coarse_near_exact=coarse,shortlist=shortlist,inventory=inventory,
        scope='Whole mesh owners >=100 triangles, compact hull <128 facets and <75% source triangles; coarse512 area samples then per-facet projected coverage. Not exhaustive. No adoption or source changes.'),indent=2)+'\n')


if __name__=='__main__':
    if '--global' in __import__('sys').argv:global_scan()
    else:main()
