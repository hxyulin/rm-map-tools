#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Save flat-back measurements and hashes without generated meshes."""
import argparse,hashlib,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('out',type=Path);ap.add_argument('--prefix',choices=['flat','front'],default='flat');a=ap.parse_args()
    for name in ['summary.json','validation.json']:
        raw=(a.out/name).read_bytes();value=json.loads(raw)
        for component in value.get('components',[]):
            proofs=[component.get('flat_back')]+[surface['native_profiles'] for surface in component.get('derived_fronts',[])]
            for proof in proofs:
                if not proof:continue
                for profile in proof['profiles']:
                    holes=profile.pop('holes');profile['filled_small_holes']=sum(h['filled'] for h in holes);profile['retained_opening_width_bounds_mm']=[h['width_upper_bound_mm'] for h in holes if not h['filled']]
        value['full_report_sha256']=hashlib.sha256(raw).hexdigest();Path(__file__).with_name(a.prefix+'-'+name).write_text(json.dumps(value,indent=2)+'\n')
if __name__=='__main__':main()
