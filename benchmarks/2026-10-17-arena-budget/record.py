#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record the complete source-pinned arena ledger without generated meshes."""
import argparse
import json
from pathlib import Path
from run import ROOT
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve(); summary = json.loads((out / 'summary.json').read_bytes()); review = json.loads((out / 'review.json').read_bytes())
    if summary['producer_sha256'] != digest(Path(__file__).with_name('run.py')) or review['producer_sha256'] != digest(Path(__file__).with_name('review.py')) or review['summary_sha256'] != digest(out / 'summary.json'): raise ValueError('stale arena report')
    if digest(out / 'candidate-field.glb') != summary['assembly']['glb_sha256']: raise ValueError('assembled field changed')
    prior = json.loads((ROOT / 'out/rmuc2027-game-lods/composition.json').read_bytes()); previous = {r['id']: r for r in prior['components']}; exact = 0
    for r in summary['components']:
        if digest(ROOT / r['visual_glb']) != r['visual_sha256']: raise ValueError('visual changed')
        if r['id'] != 'energy-unit/unit':
            if r['visual_sha256'] != previous[r['id']]['candidate_sha256']: raise ValueError('another definition changed')
            exact += 1
        if r['collision_glb'] and digest(ROOT / r['collision_glb']) != r['collision_sha256']: raise ValueError('collider budget source changed')
    if exact != 115: raise ValueError('incomplete arena')
    result = {**summary, 'review': review, 'exact_other_visual_definitions': exact, 'summary_sha256': digest(out / 'summary.json'), 'review_sha256': digest(out / 'review.json'), 'record_producer_sha256': digest(__file__)}
    Path(__file__).with_name('results.json').write_text(json.dumps(result, indent=2) + '\n'); print(summary['totals'])


if __name__ == '__main__': main()
