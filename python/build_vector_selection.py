#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build/reload a portable vector IR selection and measure tolerance-driven exports."""
import argparse
from dataclasses import asdict
import hashlib
import json
import shutil
from pathlib import Path
import time

from cad_document import CadDocument
from cad_vector_ir import FitPolicy,VectorIR,build_vector_ir,VECTOR_CONTRACT
from cad_shape_fitting import native_spline_sample_error
import numpy as np


def build(source,findings_path,output,*,policy=None):
    if output.exists():raise FileExistsError(output)
    policy=policy or FitPolicy();findings=json.loads(findings_path.read_text());before=time.perf_counter()
    with CadDocument.from_step(source,workers=1,intern_layers=True) as document:
        layer=build_vector_ir(document,findings,policy=policy)
        native_errors=[native_spline_sample_error(document,use.source_edge_id,layer.geometries[use.fallback].evaluator().value(np.linspace(0,1,129))) for use in layer.uses]
        document.verify_source()
    output.mkdir(parents=True)
    layer.write(output/'vectors.json')
    shutil.copyfile(Path(__file__).resolve().parents[1]/'NOTICE.md',output/'NOTICE.md')
    reloaded=VectorIR.read(output/'vectors.json')
    decisions=[{'source_edge_id':use.source_edge_id,'components':use.components,**json.loads(use.decision)} for use in layer.uses]
    exports=[]
    for tolerance in (1.,.1,.01,.001):
        records=[]
        for use in layer.uses:
            points,record=reloaded.export_curve(use.source_edge_id,tolerance)
            if record['total_error_bound_mm']>tolerance:raise ValueError('export exceeded requested error')
            records.append(record)
        exports.append({'requested_total_error_mm':tolerance,'segments':sum(record['segments'] for record in records),
                        'source_fallbacks':sum(record['source_fallback'] for record in records),'curves':records})
    report={'_license':'MIT OR Apache-2.0','_copyright':'Copyright (c) 2026 hxyulin <hxyulin@proton.me>',
            'copyright_scope':'report structure and tooling; source CAD and its measurements retain their upstream ownership',
            'contract':asdict(VECTOR_CONTRACT),'schema_version':1,'source_sha256':layer.source_sha256,'findings_sha256':hashlib.sha256(findings_path.read_bytes()).hexdigest(),
            'policy':asdict(policy),'curve_uses':len(layer.uses),'vector_definitions':len(layer.geometries),
            'accepted_fits':sum(decision['accepted'] for decision in decisions),
            'polygon_templates':len(layer.polygons),'accepted_polygon_templates':sum(json.loads(p.decision)['accepted'] for p in layer.polygons),
            'polygon_decisions':[{'source_face_id':p.source_face_id,'original_corners':len(p.vertex_ids),
               'template_corners':len(p.corner_indices),'recognized_model':p.recognized_model,**json.loads(p.decision)} for p in layer.polygons],'decisions':decisions,'exports':exports,
            'vectors_bytes':(output/'vectors.json').stat().st_size,'vectors_sha256':hashlib.sha256((output/'vectors.json').read_bytes()).hexdigest(),
            'source_spline_native_max_error_mm':max(native_errors,default=0.),'portable_readback':True,'source_unchanged':True,'elapsed_seconds':time.perf_counter()-before,
            'scope':'selected finite parametric curves and polygon boundary templates; not native face/solid replacements, full-field export or runtime triangle savings',
            'producer_sha256':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in ('cad_vector_ir.py','build_vector_selection.py','export_vector_selection.py')}}
    with (output/'summary.json').open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False);stream.write('\n')
    print('accepted',report['accepted_fits'],'of',len(layer.uses),'curve uses',flush=True)
    for export in exports:print(export['requested_total_error_mm'],'mm:',export['segments'],'segments;',export['source_fallbacks'],'source fallbacks',flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--findings',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--max-fit-error-mm',type=float,default=.25)
    parser.add_argument('--feature-fraction',type=float,default=.005)
    args=parser.parse_args();build(args.source,args.findings,args.out,policy=FitPolicy(max_error_mm=args.max_fit_error_mm,feature_fraction=args.feature_fraction))
