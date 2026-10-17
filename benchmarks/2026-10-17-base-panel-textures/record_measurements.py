#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record panel/texture qualifications without generated mesh/IR payloads."""
import hashlib,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('previous',ROOT/'benchmarks/2026-10-17-base-shells/record_measurements.py');previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)


def main():
    for source,target in [('rmuc2027-base-panel-trials/summary.json','panel-trials.json'),('rmuc2027-base-panel-trials/4202749/optimization.json','panel-optimization.json'),('rmuc2027-base-panel-trials/4196198/optimization.json','rear-panel-alternative.json'),('rmuc2027-base-panel-trials/4202749/qualification.json','panel-qualification.json'),('rmuc2027-base-logo-texture/summary.json','logo.json'),('rmuc2027-base-groove-texture/summary.json','groove-rejected.json'),('rmuc2027-base-panels-final/composition.json','panels-composition.json'),('rmuc2027-base-textures-final/composition.json','textures-composition.json'),('rmuc2027-base-panel-texture-review/validation.json','validation.json')]:
        path=ROOT/'out'/source;report=previous.compact(json.loads(path.read_bytes()));report['full_generated_ledger_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(Path(__file__).parent/target).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
