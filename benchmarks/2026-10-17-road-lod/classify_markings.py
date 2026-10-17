#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build a source-owned, reviewable terrain marking role catalog.

User-directed markings are visual-only. Explicit border bodies plus thin white
marking solids are whole-component exclusions. White cap patches integrated in
structural bodies require a replacement collision backing before face exclusion.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.gp import gp_Trsf
from audit_geometry import compound
from cad_document import CadDocument
from cad_patch_matching import exact_point
from p21split import Splitter
from plan_cad_lods import digest
from validate_parts import read_part


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--hierarchy',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    hierarchy=json.loads(args.hierarchy.read_text());audit=json.loads(args.audit.read_text())
    if audit['source_sha256']!=hierarchy['files_sha256']['field.step']:raise ValueError('audit source mismatch')
    selected={r['id'] for r in audit['components']};entries=[]
    borders={'red-road-surface/body-3789460','blue-road-surface/body-3807298'}
    explicit=borders|{'fortress-structure/body-4058278','fortress-structure/body-4058737','fortress-structure/body-4059105'}
    palette={'1.0000,1.0000,1.0000','1.0000,0.0271,0.0271','0.0660,0.0040,0.5930','1.0000,0.0000,0.0000','0.0000,0.0000,1.0000'}
    with CadDocument.from_step(args.source,workers=1,intern_layers=True) as document,tempfile.TemporaryDirectory() as tmp:
        if document.source_sha256!=audit['source_sha256']:raise ValueError('source mismatch')
        ix=document.index;splitter=Splitter(ix,document.model)
        for c in hierarchy['components']:
            if c['id'] not in selected:continue
            paint=[f for f in c['face_ids'] if document.model.surface_colour(ix.r(f)) in palette]
            if not paint and c['id'] not in explicit:continue
            whole=c['id'] in explicit;thickness=None
            if paint and not whole and len(c['solid_body_ids'])==1 and not c['shell_ids_by_body']:
                face=ix.r(paint[0]);surface=ix.refs_of(face)[-1]
                if ix.tname(ix.r(surface))!='PLANE':raise ValueError('paint candidate is not planar')
                frame=ix.refs_of(ix.r(surface))[0];direction=ix.refs_of(ix.r(frame))[1]
                n=np.array(exact_point(ix,int(direction)),float);n/=np.linalg.norm(n)
                seed=np.eye(3)[np.argmin(abs(n))];u=np.cross(seed,n);u/=np.linalg.norm(u);v=np.cross(n,u)
                path=Path(tmp)/'component.step';mask,rewritten=splitter.closure_products([ix.r(c['export_product_id'])]);splitter.write_closure(mask,rewritten,path)
                native,reader,error=read_part(str(path))
                if error:raise ValueError(error)
                transform=gp_Trsf();transform.SetValues(*np.column_stack((np.array([u,v,n]),np.zeros(3))).ravel())
                moved=BRepBuilderAPI_Transform(compound(native),transform,True).Shape();box=Bnd_Box();BRepBndLib.AddOptimal_s(moved,box,False,False)
                thickness=box.CornerMax().Z()-box.CornerMin().Z()
                whole=whole or thickness<=1.50001
                del native,reader
            entries.append({'component_id':c['id'],'role':'marking','visual':True,'collision':False,
                            'selection':'component' if whole else 'faces',
                            'source_face_ids':c['face_ids'] if whole else paint,
                            'backing_required':not whole,
                            'evidence':'User-directed visual-only colored border' if c['id'] in borders else
                                       'Previously reviewed separate fortress marking body' if c['id'] in explicit else
                                       'Groundwork source painted cap; whole solid selected only with <=1.5 mm native slab thickness',
                            'paint_cap_source_face_ids':paint,'native_slab_thickness_mm':thickness})
            print(c['id'],'whole' if whole else 'caps require backing',thickness,flush=True)
        document.verify_source()
    result={'schema_version':1,'source_sha256':audit['source_sha256'],'hierarchy_sha256':digest(args.hierarchy),
            'scope':'Reviewed RMUC2027 groundwork markings. Unclassified geometry retains collision. '
                    'Integrated face patches must receive unpainted backing before omission.',
            'entries':entries,'generator_sha256':digest(__file__),'audit_sha256':digest(args.audit)}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
