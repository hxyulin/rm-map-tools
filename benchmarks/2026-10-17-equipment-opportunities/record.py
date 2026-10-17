#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Retain compact audit and validation evidence without generated mesh arrays."""
import argparse,hashlib,importlib.util,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args();p=Path(__file__).resolve().parents[1]/'2026-10-17-equipment-pipeline/record.py';spec=importlib.util.spec_from_file_location('compact',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    for name in ['audit.json','fan-trial.json','review.json','cavities.json','cavity-preview.json']:
        raw=(a.out/name).read_bytes();result=m.compact(json.loads(raw));result['full_report_sha256']=hashlib.sha256(raw).hexdigest();Path(__file__).with_name(name).write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
