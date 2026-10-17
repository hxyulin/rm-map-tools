#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Assemble the 16-section road candidate with all approved equipment unchanged."""
import argparse
import copy
import json
from pathlib import Path
from run import ROOT, module
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); out = args.out.resolve()
    source = ROOT / 'out/rmuc2027-residual-equipment/composition.json'; original = json.loads(source.read_bytes())
    roads = json.loads((out / 'summary.json').read_bytes()); overrides = {r['id']: r for r in roads['components']}; rows = []
    for prior in original['components']:
        row = copy.deepcopy(prior); cid = row['id']
        for key in ['glb', 'sha256', 'triangles']: row['reference_' + key] = prior['candidate_' + key]
        if cid in overrides:
            change = overrides[cid]; variant = next(v for v in change['variants'] if v['sections_per_wave'] == 16)
            path = out / cid / 'sections-16.glb'
            if digest(path) != variant['glb_sha256'] or change['reference_triangles'] != row['reference_triangles'] or change['uses'] != row['uses'] or change['source_step_sha256'] != row['source_step_sha256']: raise ValueError('road override mismatch')
            row.update(candidate_glb=str(path.relative_to(ROOT)), candidate_sha256=digest(path), candidate_triangles=variant['triangles'], policy='native-shared-edge-extrusion-16-sections-per-wave')
        row['placed_triangles'] = row['candidate_triangles'] * row['uses']; row['placed_saving'] = (row['reference_triangles'] - row['candidate_triangles']) * row['uses']; rows.append(row)
    summary = {'schema': 'rm-game-lod-composition-v1', 'complete': True, 'components': rows,
               'source_sha256': original['source_sha256'], 'hierarchy_sha256': original['hierarchy_sha256'],
               'reference_placed_triangles': sum(r['reference_triangles'] * r['uses'] for r in rows), 'candidate_placed_triangles': sum(r['placed_triangles'] for r in rows),
               'reference_composition_sha256': digest(source), 'road_summary_sha256': digest(out / 'summary.json'), 'producer_sha256': digest(__file__)}
    (out / 'composition.json').write_text(json.dumps(summary, indent=2) + '\n')
    hp = ROOT / 'out/rmuc2027-hierarchy/hierarchy.json'
    if digest(hp) != summary['hierarchy_sha256']: raise ValueError('hierarchy changed')
    assembly = module('assembly', ROOT / 'benchmarks/2026-10-17-composed-pipeline/assemble.py')
    results = [assembly.build(out, summary, json.loads(hp.read_bytes()), s) for s in ['reference', 'candidate']]
    (out / 'assembly.json').write_text(json.dumps({'composition_sha256': digest(out / 'composition.json'), 'stages': results, 'producer_sha256': digest(__file__)}, indent=2) + '\n')
    print([(r['stage'], r['placed_triangles'], r['bytes']) for r in results])


if __name__ == '__main__': main()
