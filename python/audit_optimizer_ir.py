#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measure source-backed optimizer recipes and exact normalization on real CAD."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import time

from cad_document import CadDocument
from cad_optimizer import build_optimizer_ir


def audit(source, output, *, hierarchy=None):
    output=Path(output)
    if output.exists():
        raise FileExistsError(output)
    start=time.perf_counter(); results=[]
    with CadDocument.from_step(source,workers=1,intern_layers=True) as doc:
        loaded=time.perf_counter()-start
        for normalize, directions in ((False,False),(True,False),(False,True)):
            before=time.perf_counter()
            ir=build_optimizer_ir(doc,normalize_decimals=normalize,normalize_directions=directions,hierarchy=hierarchy)
            built=time.perf_counter()-before
            print('IR built:',normalize,directions,built,ir.geometry.statistics()['recipe_definitions'],flush=True)
            before=time.perf_counter(); proof=ir.validate(); validation=time.perf_counter()-before
            results.append({'normalize_exact_decimals':normalize,'normalize_direction_ratios':directions,'build_seconds':built,'validation_seconds':validation,
                            'geometry':ir.geometry.statistics(),'appearance':ir.appearance.statistics(),
                            'analytic':ir.analytic.statistics(),'proof':proof,
                            'affine':ir.affine.statistics(),
                            'unit_profile':json.loads(ir.units),
                            'source_hierarchy_sha256':hashlib.sha256(ir.source_hierarchy).hexdigest() if ir.source_hierarchy else None})
            print('validated:',normalize,proof,flush=True)
            del ir;gc.collect()
        report={'schema_version':1,'input_step_sha256':doc.source_sha256,'input_bytes':doc.index.size,
                'load_seconds':loaded,'results':results,
                'scope':'In-memory source-backed recipes; source identity/incidence and metadata remain in CadDocument. Recipe counts/bytes are not standalone archive savings or mesh triangle reductions.',
                'passes':['intern-ordered-recipes-v1','optional-exact-decimals-v1','optional-direction-ratios-v1','factor-analytic-frames-v1','unit-analytic-affine-v1'],
                'producer_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ('cad_optimizer.py','audit_optimizer_ir.py','p21index.py','cad_document.py','cad_passes.py')}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:
        json.dump(report,stream,indent=2);stream.write('\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--hierarchy',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();audit(args.source,args.out,hierarchy=args.hierarchy)


if __name__=='__main__':main()
