# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Independently check whole-definition coverage and completed export packages."""
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'python'))
from cad_composition import verify_composition


def main():
    out=REPO/'out/appearance-review-v2'
    review=json.loads((out/'review.json').read_text())
    catalog=json.loads((REPO/'out/terrain-review/catalog.json').read_text())
    if review['source_sha256']!=catalog['source_sha256']:
        raise ValueError('source mismatch')
    for definition in review['definitions']:
        expected=sum(c['source_faces'] for c in catalog['components'] if c['product_id']==definition['product_id'])
        if definition['native_faces']!=expected:
            raise ValueError(f'native definition face coverage changed: {definition["name"]}')
    errors={}
    for composition in review['compositions']:
        folder=out/'compositions'/composition['name']
        errors[composition['name']]=verify_composition(folder,review['source_sha256'])
        print(composition['name'],errors[composition['name']],'m bounds difference',flush=True)
    print(len(review['definitions']),'complete definitions checked;',len(errors),'compositions checked',flush=True)
    (out/'verification.json').write_text(json.dumps({'native_definition_coverage':True,'step_glb_bounds_errors_m':errors},indent=2)+'\n')


if __name__=='__main__': main()
