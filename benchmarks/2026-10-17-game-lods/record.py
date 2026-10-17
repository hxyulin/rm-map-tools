#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Keep compact source-pinned measurements; large geometry remains regenerable."""
import argparse
import json
from pathlib import Path
from run import ROOT
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); out = args.out.resolve()
    read = lambda name: json.loads((out / name).read_bytes())
    roads = read('summary.json'); collision = read('collision-summary.json'); assembly = read('assembly.json'); validation = read('validation.json'); review = read('review.json')
    if roads['producer_sha256'] != digest(Path(__file__).with_name('run.py')) or collision['producer_sha256'] != digest(Path(__file__).with_name('collision.py')) or review['producer_sha256'] != digest(Path(__file__).with_name('review.py')): raise ValueError('stale producer report')
    if review['road_summary_sha256'] != digest(out / 'summary.json') or review['collision_summary_sha256'] != digest(out / 'collision-summary.json') or validation['composition_sha256'] != digest(out / 'composition.json'): raise ValueError('stale downstream report')
    compact = []
    for row in collision['components']:
        record = {k: v for k, v in row.items() if k != 'members'}
        record.update(member_count=len(row['members']), changed_members=sum(r['input_triangles'] != r['output_triangles'] for r in row['members']),
                      retained_members=sum(r['input_triangles'] == r['output_triangles'] for r in row['members']))
        compact.append(record)
    report = {'roads': roads, 'equipment_collision': compact,
              'assembly': [{k: v for k, v in row.items() if k != 'definitions'} for row in assembly['stages']],
              'validation': validation, 'review': review,
              'reports_sha256': {name: digest(out / name) for name in ['summary.json', 'collision-summary.json', 'composition.json', 'assembly.json', 'validation.json', 'review.json']},
              'producers_sha256': {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), *[Path(__file__).with_name(n) for n in ['run.py', 'collision.py', 'compose.py', 'validate.py', 'review.py']], ROOT / 'python/cad_extrusion_skin.py', ROOT / 'python/cad_collision_proxy.py']},
              'scope': 'Inspection-only candidates. Source-native road profile checks and finite mesh comparisons; 112 other approved visual definitions byte retained. Collision subtotals are experimental relative to selected approved visuals, not installed/world totals. No runtime performance measurement.'}
    target = Path(__file__).with_name('results.json'); target.write_text(json.dumps(report, indent=2) + '\n'); print(target)


if __name__ == '__main__': main()
