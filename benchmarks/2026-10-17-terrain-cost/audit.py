#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Rebuild a source-native terrain cost baseline, without editing CAD or runtime.

CAD/meshes are scratch output; local face ordinals are qualified by component
STEP SHA, not claimed to be original STEP face IDs. Thinness/color are discovery
hints only and never classify a surface as removable paint or decoration.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'python'))
import numpy as np
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.TopAbs import TopAbs_WIRE
from OCP.TopExp import TopExp
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
from cad_document import CadDocument
from export_field_package import GlbWriter
from mesh_parts import tessellate
from p21split import Splitter
from plan_cad_lods import build_plan, digest
from validate_parts import read_part


def bounds(shape):
    box=Bnd_Box();BRepBndLib.AddOptimal_s(shape,box,False,False)
    return [[p.X(),p.Y(),p.Z()] for p in (box.CornerMin(),box.CornerMax())]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--hierarchy',type=Path,required=True)
    parser.add_argument('--root-product',type=int,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--include-source-product',type=int,action='append',default=[],
                        help='Explicit ground-bearing product outside the terrain branch; repeatable')
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    hierarchy_sha=digest(args.hierarchy)
    catalog=json.loads(args.hierarchy.read_text());plan=build_plan(catalog)
    roots=[n for n in plan['nodes'] if n['product_id']==args.root_product]
    if len(roots)!=1:raise ValueError('select one explicit placed hierarchy root')
    root=roots[0]
    component_map={c['id']:c for c in catalog['components']}
    available={c['source_product_id'] for c in catalog['components']}
    if set(args.include_source_product)-available:raise ValueError('unknown included source product')
    uses=[n for n in plan['nodes'] if n['component_id'] and
          (n['id'].startswith(root['id']+'/') or
           component_map[n['component_id']]['source_product_id'] in args.include_source_product)]
    occurrences=defaultdict(list)
    for use in uses:occurrences[use['component_id']].append(use)
    args.out.mkdir(parents=True)
    records=[];start=time.perf_counter()
    with CadDocument.from_step(args.source,workers=1,intern_layers=True) as document:
        if document.source_sha256!=catalog['files_sha256']['field.step']:raise ValueError('source mismatch')
        splitter=Splitter(document.index,document.model)
        for component in catalog['components']:
            cid=component['id']
            if cid not in occurrences:continue
            folder=args.out/cid;folder.mkdir(parents=True)
            mask,rewritten=splitter.closure_products([document.index.r(component['export_product_id'])])
            splitter.write_closure(mask,rewritten,folder/'source.step')
            native,reader,error=read_part(str(folder/'source.step'))
            if error:raise ValueError(error)
            faces=[];stats={}
            def observe(index,face,triangles):
                surface=BRepAdaptor_Surface(face);kind=str(surface.GetType()).rsplit('_',1)[-1]
                wires=IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher();TopExp.MapShapes_s(face,TopAbs_WIRE,wires)
                record={'native_face_index':index,'surface':kind,'triangles':triangles,
                        'inner_wires':max(0,wires.Extent()-1),'bbox_mm':bounds(face)}
                if kind=='Plane':
                    direction=surface.Plane().Axis().Direction()
                    record['plane_normal']=[direction.X(),direction.Y(),direction.Z()]
                faces.append(record)
            points,triangles,ci,colours=tessellate(native,.4,.25,stats,observe)
            if stats.get('unmeshed_faces') or len(faces)!=component['face_count']:raise ValueError('incomplete face mesh')
            offset=0
            for face in faces:
                count=face['triangles'];keys={colours[int(i)] for i in ci[offset:offset+count]}
                if count and len(keys)!=1:raise ValueError('unexpected mixed material within native face')
                face['source_colour']=next(iter(keys)) if keys else None
                offset+=count
            if offset!=len(triangles):raise ValueError('face/triangle accounting mismatch')
            by_surface=Counter()
            for face in faces:by_surface[face['surface']]+=face['triangles']
            by_colour=Counter(colours[int(i)] or 'unstyled' for i in ci)
            low,high=points.min(axis=0),points.max(axis=0);span=high-low
            writer=GlbWriter(cid,{'version':'2.0','generator':'terrain-cost/audit.py; upstream DJI/RoboMaster source geometry'})
            writer.add_node(cid,points/1000,triangles,[colours[int(i)] for i in ci]);writer.write(folder/'visual.glb')
            record={'id':cid,'source_product_id':component['source_product_id'],
                    'scope_group':'terrain-branch' if any(u['id'].startswith(root['id']+'/') for u in occurrences[cid]) else 'supplemental-ground-bearing',
                    'source_faces':component['face_count'],
                    'source_face_ids':component['face_ids'],
                    'component_step_sha256':digest(folder/'source.step'),
                    'visual_sha256':digest(folder/'visual.glb'),
                    'triangles':len(triangles),'placed_uses':len(occurrences[cid]),
                    'placed_triangles':len(triangles)*len(occurrences[cid]),
                    'bbox_mm':[low.tolist(),high.tolist()],'span_mm':span.tolist(),
                    'thin_unit_hint':bool(min(span)<=2),
                    'horizontal_thin_unit_hint':bool(span[2]<=2),
                    'triangles_by_surface':dict(by_surface),'triangles_by_source_colour':dict(by_colour),
                    'source_colour_complete':None not in colours,'tessellation_stats':stats,
                    'faces':faces,'occurrences':occurrences[cid]}
            records.append(record)
            print(cid,len(triangles),'triangles',dict(by_surface),flush=True)
            del native,reader,writer,points,triangles
        document.verify_source()
        source_sha=document.source_sha256
    if digest(args.hierarchy)!=hierarchy_sha:raise ValueError('hierarchy changed')
    records.sort(key=lambda r:r['placed_triangles'],reverse=True)
    report={'effect':'read-only source-native terrain audit','source_sha256':source_sha,
            'hierarchy_sha256':hierarchy_sha,'root_product_id':args.root_product,
            'root_name':root['name'],'included_source_products':args.include_source_product,'tessellation':{'linear_deflection_mm':.4,'angular_deflection_rad':.25},
            'summary':{'definitions':len(records),'placed_uses':len(uses),
                       'source_faces':sum(r['source_faces'] for r in records),
                       'definition_triangles':sum(r['triangles'] for r in records),
                       'placed_triangles':sum(r['placed_triangles'] for r in records),
                       'all_source_colours_resolved':all(r['source_colour_complete'] for r in records)},
            'components':records,'elapsed_seconds':time.perf_counter()-start,
            'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in
                               [Path(__file__),ROOT/'python/mesh_parts.py',ROOT/'python/plan_cad_lods.py']},
            'scope':'native tessellation of reviewed terrain hierarchy and explicitly included ground-bearing products; not live runtime counts or optimized LODs. '
                    'Native face indices scoped by component STEP checksum, not original source face IDs. '
                    'Thinness, color and surface type are discovery hints, not decoration/removal classifications.'}
    (args.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['summary'],indent=2),flush=True)


if __name__=='__main__':main()
