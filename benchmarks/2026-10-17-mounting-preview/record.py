#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record compact native preview proofs and comparisons, excluding mesh payloads."""
import argparse,hashlib,json
from pathlib import Path

ARRAYS={'unchanged_input_triangle_indices','native_face_indices','source_openings','native_inner_wire_indices'}
def compact(value):
    if isinstance(value,list):return [compact(v) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,item in value.items():
        if key in ARRAYS:result[key+'_count']=len(item);result[key+'_sha256']=hashlib.sha256(json.dumps(item,separators=(',',':')).encode()).hexdigest()
        else:result[key]=compact(item)
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args()
    for name in ['summary.json','review.json']:
        raw=(a.out/name).read_bytes();value=compact(json.loads(raw));value['full_report_sha256']=hashlib.sha256(raw).hexdigest();Path(__file__).with_name(name).write_text(json.dumps(value,indent=2)+'\n')
if __name__=='__main__':main()
