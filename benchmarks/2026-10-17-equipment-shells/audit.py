#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Count expensive connected pieces inside the approved rigid equipment members."""
import json
from pathlib import Path
from common import ROOT,read_mesh
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

if __name__=='__main__':
    ledger=json.loads((ROOT/'out/rmuc2027-dart-outpost/summary.json').read_bytes());rows=[]
    for r in ledger['components']:
        if not r['id'].startswith(('dart-station/','outpost/')):continue
        d=read_mesh(ROOT/r['visual_glb']);p,t,u=[d[k]for k in ['positions_mm','triangles','unit_ids']];pieces=[]
        for unit in np.unique(u):
            mask=u==unit;g=p[t[mask]];v,inv=np.unique(np.round(g.reshape(-1,3)/.01).astype(np.int64),axis=0,return_inverse=True);f=inv.reshape(-1,3);edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);count,label=connected_components(coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(v),len(v))).tocsr(),directed=False);parts=label[f[:,0]]
            for part in range(count):
                sub=g[parts==part];pieces.append({'member':int(unit),'triangles':len(sub),'span_mm':np.ptp(sub.reshape(-1,3),axis=0).tolist(),'bounds_mm':[sub.min((0,1)).tolist(),sub.max((0,1)).tolist()]})
        pieces.sort(key=lambda v:-v['triangles']);record={'id':r['id'],'triangles':len(t),'pieces':pieces};rows.append(record);print(r['id'],len(t),'pieces',len(pieces),'top',[(p['member'],p['triangles'],np.round(p['span_mm'],1).tolist())for p in pieces[:12]],flush=True)
    out=ROOT/'out/rmuc2027-equipment-shells';out.mkdir(parents=True,exist_ok=True);(out/'pieces.json').write_text(json.dumps({'components':rows},indent=2)+'\n')
