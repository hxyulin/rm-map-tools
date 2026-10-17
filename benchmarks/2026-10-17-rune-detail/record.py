#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record compact reproducible Rune measurements without generated meshes."""
import argparse,hashlib,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);a=ap.parse_args()
    for name in ['summary.json','validation.json']:
        raw=(a.out/name).read_bytes();value=json.loads(raw)
        for component in value.get('components',[]):
            for unit in component['units']:unit.pop('guard',None)
        value['full_report_sha256']=hashlib.sha256(raw).hexdigest();Path(__file__).with_name(name).write_text(json.dumps(value,indent=2)+'\n')
if __name__=='__main__':main()
