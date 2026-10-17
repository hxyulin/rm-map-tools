#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Retain compact global mounting-detail measurements; full locators stay generated."""
import argparse,hashlib,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('report',type=Path);a=ap.parse_args();raw=a.report.read_bytes();r=json.loads(raw);f=r['findings'];fields=['source_bodies','unowned_body_definitions','source_face_definitions','source_unit_definitions','opening_mouths','circular_opening_mouths','narrow_noncircular_opening_mouths','possible_fastener_units','name_supported_fastener_units','policy','opening_skips','fastener_skips','interpretation'];summary={key:r[key] for key in ['schema_version','pass_id','source_sha256','source_bytes','source_unchanged','hierarchy_sha256','producer_sha256','elapsed_seconds','scope']};summary.update(full_report_sha256=hashlib.sha256(raw).hexdigest(),findings={key:f[key] for key in fields},coaxial_opening_families=len(f['coaxial_opening_families']),components=r['components'],examples={'openings':f['openings'][:3],'possible_fasteners':f['fasteners'][:3]});Path(__file__).with_name('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if __name__=='__main__':main()
