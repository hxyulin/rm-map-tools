#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Retain compact source-bound composition metrics, excluding CAD/mesh payloads."""
import argparse, hashlib, json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('out',type=Path); a=ap.parse_args()
    for name in ['summary.json','assembly.json','review.json','validation.json']:
        raw=(a.out/name).read_bytes(); report=json.loads(raw)
        if name=='summary.json':
            for component in report['components']:
                operations=component.pop('shell_operations')
                component['shell_operations_sha256']=hashlib.sha256(json.dumps(operations,separators=(',',':')).encode()).hexdigest()
                component['shell_operation_counts']={op:sum(r['operation']==op for r in operations) for op in sorted({r['operation'] for r in operations})}
                guards=[r['validation'] for r in operations if 'sampled_deviation_mm' in r.get('validation',{})]
                component['maximum_edited_source_lod_deviation_mm']=max((r['sampled_deviation_mm']['max'] for r in guards),default=0)
        report['full_report_sha256']=hashlib.sha256(raw).hexdigest()
        Path(__file__).with_name(name).write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
