#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record reproducible collider measurements while leaving geometry regenerable."""
import argparse
import json
from pathlib import Path
from audit import ROOT
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve(); reports = {name: json.loads((out / name).read_bytes()) for name in ['energy-summary.json', 'panels-summary.json', 'validation.json', 'review.json']}
    energy, panels, validation, review = [reports[k] for k in ['energy-summary.json', 'panels-summary.json', 'validation.json', 'review.json']]
    for name, report in [('energy.py', energy), ('panels.py', panels), ('validate.py', validation), ('review.py', review)]:
        if report['producer_sha256'] != digest(Path(__file__).with_name(name)): raise ValueError('stale producer report ' + name)
    for report in [energy, panels]:
        if report['pass_sha256'] != digest(ROOT / 'python/cad_collision_profiles.py'): raise ValueError('stale profile pass')
    for report in [validation, review]:
        if report['energy_summary_sha256'] != digest(out / 'energy-summary.json') or report['panels_summary_sha256'] != digest(out / 'panels-summary.json'): raise ValueError('stale downstream report')
    final = next(r for r in energy['variants'] if r['stage'] == 'meridian-1-24')
    rows = [{'id': energy['id'], 'uses': 12, 'visual_triangles': energy['reference_triangles'], 'previous_collision_triangles': energy['reference_triangles'], 'collision_triangles': final['triangles']}]
    rows.extend({k: r[k] for k in ['id', 'uses', 'visual_triangles', 'previous_collision_triangles', 'collision_triangles']} for r in panels['components'])
    result = {'counts': rows, 'placed_triangles': {k: sum(r[k] * r['uses'] for r in rows) for k in ['visual_triangles', 'previous_collision_triangles', 'collision_triangles']},
              **reports, 'reports_sha256': {name: digest(out / name) for name in reports},
              'producers_sha256': {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), *[Path(__file__).with_name(n) for n in ['audit.py', 'energy.py', 'panels.py', 'validate.py', 'review.py']], ROOT / 'python/cad_collision_profiles.py']},
              'scope': 'Collision-only source-profile candidates, finite source/approved comparisons and exported geometry checks. No installed collision/visual/scoring change or measured runtime speedup.'}
    Path(__file__).with_name('results.json').write_text(json.dumps(result, indent=2) + '\n'); print(result['placed_triangles'])


if __name__ == '__main__': main()
