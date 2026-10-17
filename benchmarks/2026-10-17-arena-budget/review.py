#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render the exact exterior and the simplified interior in matched source views."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from run import ROOT, module
import numpy as np
from PIL import Image
from cad_radial_profile import clip_below
from plan_cad_lods import digest
from gltf_scene import read_glb, mesh_instances


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve(); summary = json.loads((out / 'summary.json').read_bytes()); composition = json.loads((out / 'composition.json').read_bytes()); row = next(r for r in composition['components'] if r['id'] == 'energy-unit/unit')
    load = module('load', ROOT / 'benchmarks/2026-10-17-game-lods/review.py').load
    raster = module('raster', ROOT / 'benchmarks/2026-10-17-base-passes/validate_render.py').raster; metric = module('metric', ROOT / 'benchmarks/2026-10-17-base-housing-aggressive/review.py').metric
    data = {s: load(ROOT / row[s + '_glb']) for s in ['reference', 'candidate']}; cut = {}
    stop = {}; rotation = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    for stage in ['reference', 'candidate']:
        d, blob = read_glb(ROOT / row[stage + '_glb']); pieces = [p[t] @ rotation.T for _, _, p, t, mi in mesh_instances(d, blob) if d['materials'][mi]['extras']['step_colour_srgb'] is None]
        g = np.concatenate(pieces); stop[stage] = (g, np.tile([.6275] * 3, (len(g), 1)))
    for stage, (g, c) in data.items():
        p = g.reshape(-1, 3); t = np.arange(len(p)).reshape(-1, 3)
        q, f, k, _ = clip_below(p * 1000, t, np.arange(len(t)), axis=0, height_mm=0); cut[stage] = (q[f] / 1000, c[k])
    views = [('oblique', (1, .7, 1.5)), ('reverse', (-1, .7, -1.5)), ('top', (0, 1, .000001)), ('front', (0, .000001, 1)), ('back', (0, .000001, -1)), ('bottom', (0, -1, .000001)), ('side', (1, .000001, 0))]; entries = []
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'; subprocess.run([shutil.which('clang++'), '-O3', str(ROOT / 'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'), '-o', str(helper)], check=True)
        for name, parts in [('complete-energy', data), ('energy-cutaway', cut), ('retainer-only', stop)]:
            folder = out / 'review' / name; folder.mkdir(parents=True, exist_ok=True); checks = []
            for view_name, view in views:
                frames = {s: raster(g, c, parts['reference'][0], view, helper, tmp, folder / (s + '-' + view_name + '.png')) for s, (g, c) in parts.items()}; sheet = Image.new('RGB', (1200, 600))
                for j, image in enumerate(frames.values()): sheet.paste(Image.fromarray(image).resize((600, 600), Image.Resampling.LANCZOS), (600 * j, 0))
                sheet.save(folder / (view_name + '.webp'), lossless=True); checks.append({'view': view_name, **metric(frames['reference'], frames['candidate'])})
            entries.append({'id': name, 'images': str(folder.relative_to(out)), 'triangles': {s: len(g) for s, (g, c) in parts.items()}, 'views': checks}); print('reviewed', name, flush=True)
    report = {'entries': entries, 'summary_sha256': digest(out / 'summary.json'), 'source_glb_sha256': digest(ROOT / row['reference_glb']), 'candidate_glb_sha256': digest(out / 'energy-visual.glb'), 'producer_sha256': digest(__file__), 'scope': 'Twenty-one matched 1200-square two-sided source-color views of complete model, X=0 cutaway and isolated retainer; exact exterior attributes checked separately. No runtime PBR/motion validation.'}
    (out / 'review.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
