#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Fit the two engraved blue Dart motor end caps as rounded profile prisms."""
import argparse
import json
from pathlib import Path
from common import ROOT,module,read_mesh,replace_members
import numpy as np
from cad_component_detail import connected_pieces
from cad_profile_envelope import profile_envelope
from plan_cad_lods import digest


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();cid='dart-station/frame';folder=out/cid;details=json.loads((out/'detail-summary.json').read_bytes());row=next(r for r in details['components']if r['id']==cid)
    if row.get('end_cap_envelopes'):raise ValueError('caps already applied; regenerate run.py input first')
    source=folder/'caps-before.glb';(folder/'visual.glb').rename(source);data=read_mesh(source);p,t,m,u=[data[k]for k in ['positions_mm','triangles','material_ids','unit_ids']];palette=data['palette'];color=[.1333,.2902,.7451];keys=[i for i,c in enumerate(palette)if c and np.max(abs(np.array(list(map(float,c.split(','))))-color))<.00001]
    if len(keys)!=1:raise ValueError('engraved end cap material binding changed')
    key=keys[0];selected=(u==1)&(m==key);old=t[selected];labels=connected_pieces(p,old);points=[];faces=[];proofs=[];cursor=0
    for part in np.unique(labels):
        used,inv=np.unique(old[labels==part],return_inverse=True);sp,st=p[used],inv.reshape(-1,3);span=np.ptp(sp,axis=0)
        if len(st)!=3798 or not(8.69<span[0]<8.71 and 60<span[1]<62 and 63<span[2]<65):raise ValueError('source cap shape binding changed')
        q,f,proof=profile_envelope(sp,st,[1,0,0],maximum_surface_distance_mm=9);points.append(q);faces.append(f+cursor);cursor+=len(q);proofs.append(proof)
    if len(proofs)!=2:raise ValueError('expected two engraved blue end caps')
    q,f=np.concatenate(points),np.concatenate(faces);keep=(u==1)&~selected;combined_p=np.concatenate([q,p]);combined_t=np.concatenate([f,t[keep]+len(q)]);combined_m=np.r_[np.full(len(f),key,int),m[keep]];replace_members(source,folder/'visual.glb',[(combined_p,combined_t,combined_m,1)],palette,folder);count=module('counts',ROOT/'benchmarks/2026-10-17-arena-budget/run.py').counts
    record={'source_member':1,'source_material_id':key,'source_color_srgb':color,'before_triangles':len(old),'after_triangles':len(f),'caps':proofs,'input_visual_sha256':digest(source),'output_visual_sha256':digest(folder/'visual.glb'),'producer_sha256':digest(__file__),'pass_sha256':digest(ROOT/'python/cad_profile_envelope.py'),'scope':'Explicit branded motor end caps, not LEDs. Rounded convex profile, 8.7 mm source depth, engraved letters and shallow rear recesses filled. Original blue PBR retained; no scoring or contact change.'};row.update(end_cap_envelopes=record,after_visual=count(folder/'visual.glb')['placed_triangles'],visual_glb_sha256=digest(folder/'visual.glb'));(folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n');details['scope']+=' Explicit Dart branded-cap profile envelopes use a nine millimetre local surface allowance; their collision stays unchanged.';(out/'detail-summary.json').write_text(json.dumps(details,indent=2)+'\n');(out/'caps-summary.json').write_text(json.dumps(record,indent=2)+'\n');print('Dart caps',len(old),'->',len(f),'full frame',row['after_visual'],flush=True)


if __name__=='__main__':main()
