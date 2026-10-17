#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Retain profile counts/metrics; leave sampled profiles and CAD geometry ignored."""
import argparse, hashlib, json
from pathlib import Path


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('out',type=Path); a=ap.parse_args()
    for name in ['summary.json','review.json']:
        raw=(a.out/name).read_bytes(); report=json.loads(raw)
        report['full_report_sha256']=hashlib.sha256(raw).hexdigest()
        Path(__file__).with_name(name).write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
