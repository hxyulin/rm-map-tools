#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Retain compact reproducible residual-pass reports, excluding generated geometry."""
import argparse,hashlib,json
from pathlib import Path


def compact(v):
    if isinstance(v,list):return [compact(x) for x in v]
    if not isinstance(v,dict):return v
    result={}
    for k,x in v.items():
        if k=='retained_input_triangle_indices':result[k+'_count']=len(x);result[k+'_sha256']=hashlib.sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()
        else:result[k]=compact(x)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args()
    names=['audit.json','summary.json','skin-summary.json','final-summary.json','assembly.json','review.json','validation.json','color-masks.json']
    for name in names:
        raw=(a.out/name).read_bytes();v=compact(json.loads(raw))
        if name=='audit.json':
            for component in v['components']:
                all_units=component.pop('units');component['unit_count']=len(all_units);component['largest_units']=all_units[:12];component['full_unit_ledger_sha256']=hashlib.sha256(json.dumps(all_units,separators=(',',':')).encode()).hexdigest()
        v['full_report_sha256']=hashlib.sha256(raw).hexdigest();Path(__file__).with_name(name).write_text(json.dumps(v,indent=2)+'\n')
    raw=(a.out/'technology-core/tool-head/profile.json').read_bytes();v=json.loads(raw);v['full_report_sha256']=hashlib.sha256(raw).hexdigest();Path(__file__).with_name('plate-profile.json').write_text(json.dumps(v,indent=2)+'\n')
if __name__=='__main__':main()
