"""Retain original casing/recesses; simplify internal head mechanisms only."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff'
sys.path.insert(0,str(BASE))
import build as b
b.OUT=ROOT/'out/rmuc2027-core-head-side-clearance'
original_envelopes=b.envelopes
KEEP={108,81,82,1284,1296,1297,1501,1254,1255,1266,1268}
def envelopes(nodes,variant):
    shapes,definition=original_envelopes(nodes,'balanced')
    pairs=[(s,label)for s,label in zip(shapes,definition['labels'])if label not in ['left body','right body','lower end bridge','upper end bridge']]
    definition['labels']=[label for s,label in pairs]
    definition['retained_original_outer_casing_nodes']=sorted(KEEP & {108,1254,1255,1266,1268})
    definition['deliberate_changes']=['Original outer casing and both recessed side panels retained exactly.','Only internal motor mechanisms and rear support use coarse boxes.']
    return [s for s,label in pairs],definition
b.envelopes=envelopes
if __name__=='__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'build'
    if action=='build':b.main(variants=['side-clearance'],keep_override=KEEP)
    elif action in ['verify','render']:
        module=b.p.module('side_clearance_'+action,str(BASE/action)+'.py');module.main()
    elif action=='finalize':
        proof=json.loads((b.OUT/'geometry-verification.json').read_text());renders=json.loads((b.OUT/'renders.json').read_text())
        assert len(renders['views'])==24
        for row in renders['views']:assert b.scan.digest(Path(row['path']))==row['sha256']
        for row in json.loads((b.OUT/'variants.json').read_text()):
            path=Path(row['path']);r=json.loads(path.read_text());assert b.scan.digest(path)==row['sha256']
            for path,h in r['input_pins'].items():assert b.scan.digest(Path(path))==h
        hashes={str(p.relative_to(b.OUT)):b.scan.digest(p)for p in b.OUT.rglob('*')if p.is_file()and p.name not in ['final-verification.json','gallery.html']}
        (b.OUT/'final-verification.json').write_text(json.dumps(dict(geometry=proof,matched_image_count=24,artifact_sha256=hashes,installed=False),indent=2)+'\n')
        print('Verified 24 matched images, geometry and frozen inputs.')
    else:raise ValueError(action)
