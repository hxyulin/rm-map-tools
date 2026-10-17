#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Save qualification ledgers without committing generated boundary geometry."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def compact(value):
    if isinstance(value,list):return [compact(v) for v in value]
    if not isinstance(value,dict):return value
    result={k:compact(v) for k,v in value.items() if k!='boundary_vertex_positions_mm'}
    if 'boundary_vertex_positions_mm' in value:
        payload=json.dumps(value['boundary_vertex_positions_mm'],separators=(',',':')).encode();result['generated_boundary_vertex_count']=len(value['boundary_vertex_positions_mm']);result['generated_boundary_vertices_json_sha256']=hashlib.sha256(payload).hexdigest()
    return result


def main():
    folder=Path(__file__).parent
    for source,target in [('rmuc2027-base-shells-audit/audit.json','audit.json'),('rmuc2027-base-planar-skins/summary.json','planar.json'),('rmuc2027-base-crossbar-skin/summary.json','crossbar.json'),('rmuc2027-base-backing-plates/summary.json','backings.json'),('rmuc2027-base-skins-final/composition.json','skins-composition.json'),('rmuc2027-base-shells-final/composition.json','shells-composition.json'),('rmuc2027-base-shells-review/validation.json','validation.json')]:
        path=ROOT/'out'/source;report=compact(json.loads(path.read_bytes()));report['full_generated_ledger_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(folder/target).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
