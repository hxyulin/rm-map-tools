#!/usr/bin/env python3
"""Independently import selected symmetry candidates and compare OCCT shapes.

Checks shape validity, bounding boxes, area/volume and bidirectional boolean
remainders. This samples candidates; it does not validate the entire audit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Trsf
from audit_geometry import compound, bounds
from p21index import Index
from p21model import Model
from p21split import Splitter
from validate_parts import read_part


def mass(shape,volume=False):
    properties=GProp_GProps()
    method=BRepGProp.VolumeProperties_s if volume else BRepGProp.SurfaceProperties_s
    method(shape,properties)
    return abs(properties.Mass())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('index',type=Path)
    ap.add_argument('candidates',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(); args.out.mkdir(parents=True,exist_ok=False)
    candidates=json.loads(args.candidates.read_text())
    selected=candidates['matches'][:3]+[m for m in candidates['matches'] if m['type']=='MANIFOLD_SOLID_BREP'][:2]
    ix=Index(args.index)
    results=[]
    try:
        if candidates.get('source_sha256') and candidates['source_sha256'] != hashlib.sha256(ix.mm).hexdigest():
            raise ValueError('candidate source checksum does not match the STEP index')
        model=Model(ix); splitter=Splitter(ix,model)
        for group in selected:
            reference=group['bodies'][0]
            candidate=max(group['bodies'][1:],key=lambda b:np.linalg.norm(np.array(b['reference_to_body_matrix_mm'])[:3,:3]-np.eye(3)))
            shapes=[]; byte_counts=[]
            for body in [reference,candidate]:
                row=ix.r(body['id']); product=model.rep_product[model.body_rep[row]]
                mask,rewritten=splitter.closure_products([product],body_ids={body['id']})
                path=args.out/f"body-{body['id']}.step"
                splitter.write_closure(mask,rewritten,str(path))
                doc,reader,error=read_part(str(path))
                if error: raise ValueError(error)
                shapes.append(compound(doc)); byte_counts.append(path.stat().st_size)
            matrix=np.array(candidate['reference_to_body_matrix_mm'])
            transform=gp_Trsf(); transform.SetValues(*matrix[:3].ravel())
            placed=BRepBuilderAPI_Transform(shapes[0],transform,True).Shape()
            target=shapes[1]
            remainders=[]
            for a,b in [(placed,target),(target,placed)]:
                cut=BRepAlgoAPI_Cut(a,b)
                cut.Build()
                remainders.append(dict(done=bool(cut.IsDone()),area_mm2=mass(cut.Shape()) if cut.IsDone() else None))
            box_delta=float(np.max(np.abs(np.array(bounds(placed))-np.array(bounds(target)))))
            row=dict(reference_body=reference['id'],candidate_body=candidate['id'],type=group['type'],
                products=candidate['products'],extracted_step_bytes=byte_counts,
                reference_valid=bool(BRepCheck_Analyzer(placed).IsValid()),candidate_valid=bool(BRepCheck_Analyzer(target).IsValid()),
                bbox_max_delta_mm=box_delta,area_mm2=[mass(placed),mass(target)],
                volume_mm3=[mass(placed,True),mass(target,True)] if group['type']=='MANIFOLD_SOLID_BREP' else None,
                bidirectional_cut=remainders,reference_to_candidate_matrix_mm=matrix.tolist())
            results.append(row); print(json.dumps(row),flush=True)
            (args.out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    finally:
        ix.mm.close(); ix._f.close()

if __name__=='__main__':main()
