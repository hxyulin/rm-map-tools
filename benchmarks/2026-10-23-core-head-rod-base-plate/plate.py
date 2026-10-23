"""Replace the rod-root plate with one convex collider; preserve visual bytes."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-core-head-solid-rear'))
import solid
b=solid.b
BASE=ROOT/'out/rmuc2027-core-head-solid-rear/solid-rear/verification.json'
b.OUT=ROOT/'out/rmuc2027-core-head-rod-base-plate'
previous_envelopes=solid.envelopes

def envelopes(nodes,variant):
    shapes,definition=previous_envelopes(nodes,'solid-rear')
    source=np.unique(nodes[1296].reshape(-1,3),axis=0);outer=source[ConvexHull(source).vertices]
    selected,preview,recession=b.v.compact_hull(outer,tolerance=.25);center=selected.mean(0)
    shape=dict(kind='convex_hull',vertices_local_m=((selected-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1]))
    shapes.append(shape);definition['labels'].append('solid rod-base plate')
    definition.update(rod_base_plate=dict(source_node=1296,source_triangles=len(nodes[1296]),hull_vertices=len(selected),preview_triangles=len(preview),outer_vertex_recession_max_mm=recession,
        bounds_mm=[source.min(0).tolist(),source.max(0).tolist()],deliberate_changes='Fine holes and face recesses close; chamfered outer perimeter and thickness follow source convex outline.'),
        deliberate_changes=definition['deliberate_changes']+['Rod-root plate becomes one convex solid, filling its small openings and face recesses.'])
    return shapes,definition
b.envelopes=envelopes
if __name__=='__main__':
    action=sys.argv[1]if len(sys.argv)>1 else 'build'
    if action=='build':
        b.main(variants=['rod-base-plate'],keep_override=solid.rear.s.KEEP-{1254,1255,81,1297,1501,1296})
        path=b.OUT/'rod-base-plate/verification.json';r=json.loads(path.read_text());r['input_pins'][str(BASE)]=b.scan.digest(BASE);path.write_text(json.dumps(r,indent=2)+'\n')
        rows=json.loads((b.OUT/'variants.json').read_text());rows[0]['sha256']=b.scan.digest(path);(b.OUT/'variants.json').write_text(json.dumps(rows,indent=2)+'\n')
    elif action=='verify':b.p.module('rod_base_verify',str(ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/verify.py')).main(approach_exempt_labels=['solid rod cylinder','single solid lower block','solid rod-base plate'])
    elif action=='render':b.p.module('rod_base_render',str(ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/render.py')).main()
    else:raise ValueError(action)
