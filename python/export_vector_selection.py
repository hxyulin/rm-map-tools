#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Export portable vector curves at a total source-relative millimetre tolerance."""
import argparse
import json
from pathlib import Path

from cad_vector_ir import VectorIR


def export(layer,output,tolerance_mm,*,edge_ids=None):
    """Write selected finite 3D polylines with the fit/chord/roundoff budget split."""
    if output.exists():raise FileExistsError(output)
    ids=[use.source_edge_id for use in layer.uses] if edge_ids is None else list(edge_ids)
    if len(set(ids))!=len(ids):raise ValueError('duplicate requested source edge')
    curves=[]
    for edge in ids:
        points,proof=layer.export_curve(edge,tolerance_mm)
        if proof['total_error_bound_mm']>tolerance_mm:raise ValueError('export error budget exceeded')
        curves.append({**proof,'points_mm':points.tolist()})
    output.parent.mkdir(parents=True,exist_ok=True)
    polygons=[]
    if edge_ids is None:
        for polygon in layer.polygons:
            points,proof=polygon.outline(tolerance_mm);polygons.append({**proof,'points_mm':points.tolist()})
    data={'schema':'rm-cad-vector-polyline-export-v1','source_sha256':layer.source_sha256,'units':'mm',
          'geometry_notice':'Derived source CAD geometry; ownership and source terms unchanged. For DJI RoboMaster data see NOTICE.md.',
          'requested_total_error_mm':tolerance_mm,'coverage':'selected curves in source-local coordinates; not a complete field mesh',
          'curves':curves,'polygon_outlines':polygons}
    with output.open('x') as stream:json.dump(data,stream,separators=(',',':'),allow_nan=False);stream.write('\n')
    return {'curves':len(curves),'polygon_outlines':len(polygons),'segments':sum(c['segments'] for c in curves),
            'source_fallbacks':sum(c['source_fallback'] for c in curves),'bytes':output.stat().st_size}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vectors',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--tolerance-mm',type=float,required=True);parser.add_argument('--edge-id',type=int,action='append')
    args=parser.parse_args();print(export(VectorIR.read(args.vectors),args.out,args.tolerance_mm,edge_ids=args.edge_id))
