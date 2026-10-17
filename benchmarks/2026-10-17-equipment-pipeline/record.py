#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Retain compact measurements and hashes without generated geometry arrays."""
import argparse,hashlib,json
from pathlib import Path

ARRAYS={'input_triangle_indices','locked_source_vertex_indices','protected_source_vertex_indices','sample_points_mm','reference_vertex_distances_mm'}

def compact(value):
    if isinstance(value,list):return [compact(v) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key in ARRAYS:
            result[key+'_count']=len(item);result[key+'_sha256']=hashlib.sha256(json.dumps(item,separators=(',',':')).encode()).hexdigest()
        else:result[key]=compact(item)
    if isinstance(value.get('lod'),dict) and value['lod'].get('whole_unit_fallback') and value.get('sampled_deviation_mm',{}).get('max',0)>1.001:
        result['rejected_lod_sampled_deviation_mm']=result.pop('sampled_deviation_mm');result['final_check']='See review.json exported_unit_checks for retained fallback geometry.'
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args()
    for name in ['inventory.json','passes.json','review.json']:
        raw=(a.out/name).read_bytes();value=compact(json.loads(raw));value['full_report_sha256']=hashlib.sha256(raw).hexdigest();Path(__file__).with_name(name).write_text(json.dumps(value,indent=2)+'\n')

if __name__=='__main__':main()
