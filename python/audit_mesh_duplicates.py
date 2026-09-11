#!/usr/bin/env python3
"""Read-only mesh congruence audit across distinct source nodes.

Tests the 24 axis-aligned proper rotations, then 24 reflections, with arbitrary
translation. Requires a bijection of all unique vertices within tolerance and
identical oriented triangle connectivity after that mapping. Materials are
compared separately. This is evidence about meshes, not exact CAD surfaces.
"""
import argparse
from collections import defaultdict
import hashlib
from itertools import permutations, product
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial import cKDTree
from gltf_scene import read_glb_nodes


def rotations():
    result=[]
    for permutation in permutations(range(3)):
        for signs in product((-1,1),repeat=3):
            r=np.eye(3)[list(permutation)]*np.array(signs)[:,None]
            result.append(r)
    return sorted(result,key=lambda r:(np.linalg.det(r)<0,not np.array_equal(r,np.eye(3)),tuple(r.ravel())))


def triangle_order(triangles, colours=None):
    """Canonical cyclic orientation and triangle ordering; never reverse winding."""
    shift=np.argmin(triangles,axis=1)
    canonical=np.take_along_axis(triangles,(np.arange(3)[None,:]+shift[:,None])%3,axis=1)
    if colours is not None:
        canonical=np.column_stack((canonical,colours))
    # np.lexsort's last key is primary, so explicitly use column 0 last.
    order=np.lexsort(tuple(canonical[:,i] for i in reversed(range(canonical.shape[1]))))
    return canonical[order]


def prepare(name, points, triangles, colours):
    p,inverse=np.unique(points,axis=0,return_inverse=True)
    t=inverse[triangles]
    centre=(p.min(0)+p.max(0))/2
    return dict(name=name,p=p-centre,t=t,colours=colours,centre=centre,
                extent=np.ptp(p,axis=0),tree=cKDTree(p-centre),topology=triangle_order(t))


def match(reference,candidate,tolerance):
    if len(reference['p'])!=len(candidate['p']) or len(reference['t'])!=len(candidate['t']):
        return None
    colours=sorted(set(reference['colours']+candidate['colours']),key=lambda x:(x is None,x))
    colour_ids={key:i for i,key in enumerate(colours)}
    ref_coloured=triangle_order(reference['t'],[colour_ids[c] for c in reference['colours']])
    for rotation in rotations():
        if not np.allclose(reference['extent'],np.abs(rotation)@candidate['extent'],atol=2*tolerance,rtol=0):
            continue
        points=candidate['p']@rotation.T
        sample=points[np.linspace(0,len(points)-1,min(32,len(points)),dtype=int)]
        if reference['tree'].query(sample)[0].max()>tolerance:
            continue
        distance,mapping=reference['tree'].query(points)
        if distance.max()>tolerance or len(np.unique(mapping))!=len(mapping):
            continue
        triangles=mapping[candidate['t']]
        mirrored=bool(np.linalg.det(rotation)<0)
        if mirrored:
            triangles=triangles[:,[0,2,1]]
        if not np.array_equal(reference['topology'],triangle_order(triangles)):
            continue
        colours_match=np.array_equal(ref_coloured,triangle_order(triangles,[colour_ids[c] for c in candidate['colours']]))
        matrix=np.eye(4); matrix[:3,:3]=rotation
        matrix[:3,3]=reference['centre']-candidate['centre']@rotation.T
        return dict(candidate_to_reference_matrix=matrix.tolist(),mirrored=mirrored,
                    max_vertex_deviation_m=float(distance.max()),same_colours=bool(colours_match))
    return None


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('package',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--tolerance-m',type=float,default=1e-5)
    args=ap.parse_args()
    if not np.isfinite(args.tolerance_m) or args.tolerance_m<=0:
        ap.error('tolerance must be finite and positive')
    manifest=json.loads((args.package/'manifest.json').read_text())
    groups=defaultdict(list); matches=[]; inputs={}; total=0; triangles=0
    start=time.perf_counter()
    for asset,entry in manifest['assets'].items():
        if asset=='full-map': continue
        path=args.package/entry['visual']
        inputs[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for name,p,t,c in read_glb_nodes(path):
            item=prepare(f'{asset}/{name}',p,t,c)
            key=(len(item['p']),len(t))
            found=None
            for reference in groups[key]:
                found=match(reference,item,args.tolerance_m)
                if found:
                    found.update(reference=reference['name'],candidate=item['name'],triangles=len(t),vertices=len(item['p']))
                    matches.append(found); break
            if found is None:
                groups[key].append(item)
            total+=1; triangles+=len(t)
        print(f'{asset}: {total} nodes, {len(matches)} matches',flush=True)
    report=dict(method=__doc__,inputs=inputs,tolerance_m=args.tolerance_m,nodes=total,
                triangles=triangles,matches=matches,duplicate_nodes=len(matches),
                duplicate_triangles=sum(m['triangles'] for m in matches),
                duplicate_triangles_same_colours=sum(m['triangles'] for m in matches if m['same_colours']),
                elapsed_seconds=time.perf_counter()-start)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('matches','method','inputs')},indent=2),flush=True)

if __name__ == '__main__': main()
