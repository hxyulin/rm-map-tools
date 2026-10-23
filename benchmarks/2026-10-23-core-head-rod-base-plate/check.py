"""Verify the single-plate delta and unchanged prior primitive fits."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from plate import b,BASE
helpers=b.p.module('rod_plate_check_helpers',str(b.ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/verify.py'))
r=json.loads((b.OUT/'rod-base-plate/verification.json').read_text());old=json.loads(BASE.read_text())
a=json.loads(Path(r['native_review']).read_text());o=json.loads(Path(old['native_review']).read_text());parts=[p['shape']for p in a['native_parts']if p.get('source_group')];oldparts=[p['shape']for p in o['native_parts']if p.get('source_group')]
assert parts[:-1]==oldparts and len(parts)==len(oldparts)+1
_,_,n=b.scan.load_nodes(Path(r['source_collision']));source=n[1296];shape=parts[-1];target=b.v.geometry(shape)
points=np.unique(source.reshape(-1,3),axis=0);outer=points[ConvexHull(points).vertices]
recession=b.p.distances(outer,target.reshape(-1,3),np.arange(len(target)*3).reshape(-1,3))
reverse=b.p.distances(b.p.probes(target,20000),source.reshape(-1,3),np.arange(len(source)*3).reshape(-1,3))
_,_,newnodes=b.scan.load_nodes(Path(r['candidate_collision']));_,_,oldnodes=b.scan.load_nodes(Path(old['candidate_collision']))
for i in r['kept_head_nodes']:assert np.array_equal(newnodes[i],oldnodes[i])
assert recession.max()<.001
proof=dict(previous_14_head_shapes_exact=True,retained_mesh_nodes_exact_to_previous=True,source_owner=1296,source_triangles=len(source),hull_vertices=len(shape['vertices_local_m']),preview_triangles=len(target),
 convex_outer_vertex_recession_max_mm=float(recession.max()),new_surface_to_source_max_sampled_mm=float(reverse.max()),
 caveat='Convex outer boundary match does not preserve cavities: holes, central entry and face recesses become solid. Prior coarse contact/entry tradeoffs remain.')
(b.OUT/'rod-base-plate/delta-verification.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
