#!/usr/bin/env python3
"""Find STEP body candidates after rigid frame normalization, without rewriting.

Ordered geometry graphs must agree after 3D points and directions are expressed
in the body's first explicit axis frame. Scalar numeric spellings and topology
order remain significant. Quantization identifies candidates, not CAD proofs;
styles and metadata are excluded. No mirror matching is performed here.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from audit_geometry_duplicates import GeometryFingerprints
from mesh_parts import placement
from p21index import Index
from p21model import BODY_TYPES, Model, NUM_RE
from p21split import forward_closure


def frame_of(ix,body):
    seen=set(); stack=[body]
    while stack:
        row=stack.pop()
        if row<0: raise ValueError('unresolved geometry reference')
        if row in seen: continue
        seen.add(row)
        if ix.tname(row)=='AXIS2_PLACEMENT_3D':
            # Implicit direction defaults do not transform covariantly.
            if len(ix.refs_of(row))==3:
                frame=placement(ix,row)
                if np.isfinite(frame).all(): return frame
        stack.extend(reversed([ix.r(int(ref)) for ref in ix.refs_of(row)]))
    return None


class FrameFingerprints(GeometryFingerprints):
    def __init__(self,ix,frame,point_quantum_mm=1e-5,direction_quantum=1e-9):
        super().__init__(ix)
        self.origin=frame[:3,3]; self.rotation=frame[:3,:3]
        self.point_quantum=point_quantum_mm; self.direction_quantum=direction_quantum

    def entity_text(self,row):
        kind=self.ix.tname(row)
        if kind in ('CARTESIAN_POINT','DIRECTION'):
            args=self.ix.args(row)
            values=np.array([float(n) for n in NUM_RE.findall(args[args.index(b'('):])])
            if len(values)==3:
                if kind=='CARTESIAN_POINT':
                    values=(values-self.origin)@self.rotation
                    quantum=self.point_quantum
                else:
                    length=np.linalg.norm(values)
                    if not length: raise ValueError('zero direction')
                    values=(values/length)@self.rotation
                    quantum=self.direction_quantum
                normalized=np.rint(values/quantum).astype(np.int64)
                return kind.encode()+b'('+b','.join(str(int(n)).encode() for n in normalized)+b');'
        return super().entity_text(row)


def estimate_removable_geometry(ix,matches):
    """Upper bound before occurrence/style costs; exclude shared retained geometry."""
    duplicate_rows=np.array([ix.r(body['id']) for group in matches for body in group['bodies'][1:]],dtype=np.int64)
    retained_rows=np.setdiff1d(ix.rows_of(*BODY_TYPES),duplicate_rows)
    redundant=forward_closure(ix,duplicate_rows,np.zeros(ix.n,dtype=bool))
    retained=forward_closure(ix,retained_rows,np.zeros(ix.n,dtype=bool))
    removable=redundant & ~retained
    return dict(candidate_geometry_records=int(removable.sum()),
                candidate_geometry_text_bytes=int(ix.lens[removable].sum()),
                fraction_of_source_bytes=float(ix.lens[removable].sum()/ix.size),
                limitation='Candidate upper bound only: excludes replacement placements, styles, metadata, and compressed size effects; candidates are not all CAD-validated.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('index',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(); start=time.perf_counter()
    ix=Index(args.index)
    try:
        model=Model(ix); groups=defaultdict(list); skipped=0
        owners=defaultdict(set)
        for body,rep in model.bodies:
            product=model.rep_product.get(rep)
            if product is not None: owners[body].add(model.pname(product))
        bodies=ix.rows_of(*BODY_TYPES)
        for i,body in enumerate(bodies):
            body=int(body)
            frame=frame_of(ix,body)
            if frame is None:
                skipped+=1; continue
            fingerprints=FrameFingerprints(ix,frame)
            signature=fingerprints.signature(body)
            groups[signature].append(dict(id=int(ix.ids[body]),products=sorted(owners[body]),
                geometry_entities=len(fingerprints.memo),frame=frame.tolist(),type=ix.tname(body)))
            if i%5000==0: print(f'{i}/{len(bodies)} bodies, {len(groups)} normalized groups',flush=True)
        matches=[]
        for rows in groups.values():
            if len(rows)<2: continue
            reference=rows[0]
            inverse=np.linalg.inv(np.array(reference['frame']))
            items=[]
            for row in rows:
                items.append(dict(id=row['id'],products=row['products'],
                    reference_to_body_matrix_mm=(np.array(row['frame'])@inverse).tolist()))
            matches.append(dict(count=len(rows),type=reference['type'],
                representative_geometry_entities=reference['geometry_entities'],bodies=items))
        matches.sort(key=lambda group:-(group['count']-1)*group['representative_geometry_entities'])
        report=dict(source=ix.source,source_bytes=ix.size,source_sha256=hashlib.sha256(ix.mm).hexdigest(),method=__doc__,
            point_quantum_mm=1e-5,direction_quantum=1e-9,
            body_definitions=len(bodies),skipped_no_explicit_axis_frame=skipped,
            unique_normalized_fingerprints=len(groups),candidate_groups=len(matches),
            candidate_redundant_bodies=sum(m['count']-1 for m in matches),
            matches=matches,geometry_record_upper_bound=estimate_removable_geometry(ix,matches),
            elapsed_seconds=time.perf_counter()-start)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ['matches','method']},indent=2),flush=True)
    finally:
        ix.mm.close(); ix._f.close()

if __name__=='__main__': main()
