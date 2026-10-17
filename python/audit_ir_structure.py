#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check typed topology and stable identities against an entire source STEP."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from cad_document import CadDocument
from cad_optimizer import build_optimizer_ir
from cad_ir_structure import PASS_CONTRACTS


def audit(source, output, hierarchy=None):
    if output.exists():raise FileExistsError(output)
    before=time.perf_counter()
    with CadDocument.from_step(source,workers=1,intern_layers=True) as document:
        ir=build_optimizer_ir(document,hierarchy=hierarchy)
        print('source IR ready',flush=True)
        views=ir.structural_views()
        print('structural views ready',flush=True)
        built=time.perf_counter()-before;before=time.perf_counter()
        proof=views.validate(ir)
        report={'_license':'MIT OR Apache-2.0','_copyright':'Copyright (c) 2026 hxyulin <hxyulin@proton.me>',
                'schema_version':1,'source_sha256':document.source_sha256,
                'context_sha256':views.context.hex(),'build_including_load_seconds':built,
                'validation_seconds':time.perf_counter()-before,
                'typed_geometry':views.geometry.statistics(),'topology':views.topology.statistics(),
                'recipe_hash_bytes':views.recipe_hashes.nbytes,
                'body_roots':len(views.body_hashes),
                'distinct_ordered_body_graphs':len(set(digest for _,digest in views.body_hashes)),
                'body_hashes':dict(views.body_hashes),'proof':proof,
                'contracts':[asdict(value) for value in PASS_CONTRACTS],
                'scope':'Source-backed ordered graph identities, not congruence, mesh reuse, or standalone storage savings.',
                'producer_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ('cad_ir_structure.py','cad_optimizer.py','audit_ir_structure.py')}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--hierarchy',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();audit(args.source,args.out,args.hierarchy)
