#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Discover terrain faces adjacent to white planar caps; never a removal plan."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
from OCP.TopAbs import TopAbs_FACE,TopAbs_EDGE
from OCP.TopExp import TopExp
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from audit_geometry import compound
from plan_cad_lods import digest
from validate_parts import read_part


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('audit',type=Path);args=parser.parse_args()
    audit=json.loads((args.audit/'audit.json').read_text());report=[]
    for record in audit['components']:
        caps={f['native_face_index'] for f in record['faces']
              if f.get('source_colour')=='1.0000,1.0000,1.0000' and f['surface']=='Plane'}
        if not caps:continue
        source=args.audit/record['id']/'source.step'
        if digest(source)!=record['component_step_sha256']:raise ValueError('component input changed')
        native,reader,error=read_part(str(source))
        if error:raise ValueError(error)
        shape=compound(native);faces=ShapeMap();edges=ShapeMap()
        TopExp.MapShapes_s(shape,TopAbs_FACE,faces);TopExp.MapShapes_s(shape,TopAbs_EDGE,edges)
        if faces.Extent()!=len(record['faces']):raise ValueError('native face enumeration changed')
        incidence=defaultdict(set)
        for i in range(1,faces.Extent()+1):
            owned=ShapeMap();TopExp.MapShapes_s(faces.FindKey(i),TopAbs_EDGE,owned)
            for j in range(1,owned.Extent()+1):incidence[edges.FindIndex(owned.FindKey(j))].add(i)
        neighbors=set().union(*(owners for owners in incidence.values() if owners & caps))-caps
        by_index={f['native_face_index']:f for f in record['faces']}
        curved={i for i in neighbors if by_index[i]['surface']!='Plane'}
        planes=neighbors-curved
        report.append({'id':record['id'],'placed_uses':record['placed_uses'],
                       'white_planar_cap_triangles':sum(by_index[i]['triangles'] for i in caps),
                       'adjacent_curved_triangles':sum(by_index[i]['triangles'] for i in curved),
                       'adjacent_planar_triangles':sum(by_index[i]['triangles'] for i in planes),
                       'native_white_cap_indices':sorted(caps),
                       'native_adjacent_curved_indices':sorted(curved),
                       'native_adjacent_planar_indices':sorted(planes),
                       'component_step_sha256':record['component_step_sha256']})
        del native,reader
    result={'scope':'Native edge adjacency to white planar caps. Adjacent faces can be structural; '
                    'these are inspection candidates, not removable paint or certified savings. '
                    'Indices are local OCCT indices qualified by component STEP checksum.',
            'audit_sha256':digest(args.audit/'audit.json'),'components':report,
            'producer_sha256':digest(__file__)}
    target=args.audit/'paint-adjacency.json'
    with target.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    for r in report:
        if r['white_planar_cap_triangles']>100:
            print(r['id'],r['white_planar_cap_triangles'],'white caps +',
                  r['adjacent_curved_triangles'],'curved neighbors +',r['adjacent_planar_triangles'],'planar neighbors',flush=True)


if __name__=='__main__':main()
