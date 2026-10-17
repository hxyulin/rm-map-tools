#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explain closure distances with source-bore envelopes, without certifying error."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from mesh_quality import sample_points,distances
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();out=a.out;r=json.loads((out/'summary.json').read_bytes());audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());path=ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz'
    if digest(path)!=r['current_visual_sha256']:raise ValueError('reference mismatch')
    old=np.load(path);result={};trials=json.loads((out/'trial-summary.json').read_bytes())
    for u in r['units']:
        source=u['source_unit_id'];path=out/str(source)/'trial.npz'
        if digest(path)!=next(t['geometry_sha256'] for t in trials['trials'] if t['source_unit_id']==source):raise ValueError('trial mismatch')
        new=np.load(path);i=next(i for i,x in enumerate(audit['units']) if x['source_id']==source);ot=old['triangles'][old['unit_ids']==i];rows={}
        for label,pp,tt,qp,qt in [('current_to_trial',old['positions_mm'],ot,new['positions_mm'],new['triangles']),('trial_to_current',new['positions_mm'],new['triangles'],old['positions_mm'],ot)]:
            samples=sample_points(pp,tt,8192);d=distances(samples,qp,qt);inside=np.zeros(len(samples),bool)
            for bore in u['complete_bores_below_17mm']:
                start=np.array(bore['start_mm']);end=np.array(bore['end_mm']);axis=(end-start)/np.linalg.norm(end-start);delta=samples-start;z=delta@axis;rad=np.linalg.norm(delta-z[:,None]*axis,axis=1);inside|=(z>=-1)&(z<=np.linalg.norm(end-start)+1)&(rad<=bore['radius_mm']+1)
            rows[label]={'sample_count':len(d),'max_mm':float(d.max()),'samples_over_1mm':int((d>1).sum()),'over_1mm_within_source_bore_envelopes_plus_1mm':int(((d>1)&inside).sum()),'max_outside_bore_envelopes_mm':float(d[~inside].max(initial=0))}
        result[str(source)]=rows
    (out/'bore-distance-diagnostics.json').write_text(json.dumps({'units':result,'producer_sha256':digest(Path(__file__)),'scope':'Deterministic triangle sample points tested against closed-source-bore cylinders expanded by 1 mm. Explains intentional closure differences; not a continuous geometric error proof.'},indent=2)+'\n')
if __name__=='__main__':main()
