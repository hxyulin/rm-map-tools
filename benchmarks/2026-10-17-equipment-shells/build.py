#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Build the source-owned candidate with a bounded optical-retention refinement."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from common import ROOT


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);folder=Path(__file__).parent
    # Only our generated refinement state is reset. Approved input assets stay.
    for name in ['optical-guards.json','applied-optical-guards.json']:
        if (out/name).exists():(out/name).unlink()
    def run(name,*extra):subprocess.run([sys.executable,str(folder/name),'--out',str(out),*extra],cwd=ROOT,check=True)
    for attempt in range(3):
        print('optical refinement round',attempt,flush=True);run('run.py',*(['--occlusion-guards',str(out/'optical-guards.json')]if attempt else []));run('caps.py');run('compose.py');run('guard_lights.py')
        if json.loads((out/'optical-guards.json').read_bytes())['passes_light_mask_guard']:break
    else:raise ValueError('bounded source-retention refinement did not restore the primary light masks')
    run('validate.py');run('review.py')


if __name__=='__main__':main()
