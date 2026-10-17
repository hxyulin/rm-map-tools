#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Repair the experimental Low visual LOD from its approved source geometry."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
from cad_experimental_lod import export_trial
from cad_repaired_lod import visual_selector, selective_indices
from gltf_scene import read_glb
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-low-repair')
    ap.add_argument('--all-pieces', action='store_true', help='expensive conservative comparison instead of selective Low repair')
    ap.add_argument('--policy', choices=['tight', 'budget'], default='budget')
    ap.add_argument('--seal', action='store_true', help='retain source pieces named by the interior-gap plan')
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'out/rmuc2027-equipment-shells/candidate-field.glb'
    before = digest(source); name = a.policy + ('-sealed' if a.seal else '')
    target = out / (name + '-field.glb')
    policy = {} if a.policy == 'tight' else dict(structural_distance_mm=8, chromatic_distance_mm=1, allowed_bad_area_fraction=.05)
    def selector(p, t, material, primitive):
        return visual_selector(p, t, material, primitive, **policy)
    if not a.all_pieces:
        plan = json.loads((out / 'repair-plan.json').read_text())
        if plan['source_sha256'] != before: raise ValueError('source repair plan changed')
        low = ROOT / 'out/rmuc2027-ultra-lod/low-field.glb'
        if plan['low_sha256'] != digest(low): raise ValueError('Low repair plan changed')
        seal = json.loads((out / 'seal-plan.json').read_text()) if a.seal else None
        if seal and (seal['source_sha256'] != before or seal['low_sha256'] != digest(out / (a.policy + '-field.glb')) or not seal['interior_holes_only']): raise ValueError('seal plan inputs changed')
        doc, blob = read_glb(source); lookup = {}; exact = {}
        for mi, mesh in enumerate(doc['meshes']):
            for pi, prim in enumerate(mesh['primitives']):
                key = (prim['indices'], prim['attributes']['POSITION'], prim['material'])
                lookup.setdefault(key, set()).update(label for m, pr, label in plan['pieces'] if m == mi and pr == pi)
                if seal:
                    exact.setdefault(key, set()).update(fi for m, pr, fi in seal['source_triangles'] if m == mi and pr == pi)
        def selector(p, t, material, primitive):
            key = (primitive['indices'], primitive['attributes']['POSITION'], primitive['material'])
            return selective_indices(p, t, material, primitive, lookup[key], source_patch_triangles=sorted(exact.get(key, set())), **policy)
    row = export_trial(source, target, .1, index_selector=selector, align_normals=True)
    if not a.all_pieces: row['repair_plan_sha256'] = digest(out / 'repair-plan.json')
    if a.seal: row['seal_plan_sha256'] = digest(out / 'seal-plan.json')
    assert digest(source) == before
    row.update(source_sha256=before, sha256=digest(target),
        producer_sha256={str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), ROOT / 'python/cad_repaired_lod.py', ROOT / 'python/cad_experimental_lod.py']},
        scope='Inspection-only visual candidate. Seven samples per source/final triangle in each material piece. Not continuous CAD, opening, optical occlusion, motion or collision certification.')
    row['policy'] = a.policy
    (out / (name + '.json')).write_text(json.dumps(row, indent=2, allow_nan=False) + '\n')
    print(row['placed_triangles'], 'placed /', row['stored_triangles'], 'stored', flush=True)


if __name__ == '__main__': main()
