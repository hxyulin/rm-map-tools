#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare actual exported profile colliders, full definitions and selected panels."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from audit import ROOT, module
import numpy as np
from PIL import Image
from gltf_scene import read_glb, mesh_instances
from plan_cad_lods import digest
from cad_radial_profile import clip_below


def load(path, member=None):
    d, blob = read_glb(path); parts = []
    for i, _, p, t, _ in mesh_instances(d, blob):
        extra = d['nodes'][i].get('extras', {}); owner = extra.get('source_native_shell_index', extra.get('native_shell_index'))
        if member is None or owner == member: parts.append(p[t])
    return np.concatenate(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True); args = ap.parse_args(); out = args.out.resolve()
    energy = json.loads((out / 'energy-summary.json').read_bytes()); panels = json.loads((out / 'panels-summary.json').read_bytes()); composition = json.loads((ROOT / 'out/rmuc2027-residual-equipment/composition.json').read_bytes()); source = {r['id']: ROOT / r['candidate_glb'] for r in composition['components']}; cases = []
    for cid in [energy['id'], *[r['id'] for r in panels['components']]]:
        candidate = out / cid / ('meridian-1-24.glb' if cid == energy['id'] else 'panels.glb')
        previous = ROOT / 'out/rmuc2027-game-lods' / cid / 'contact-6mm.glb'
        cases.append((cid, {s: load(p) for s, p in [('reference', source[cid]), ('previous', previous), ('profile', candidate)]}))
        selected = {'dart-station/frame': [1], 'dart-station/deck-and-shared-hardware': [122, 149, 178], 'dart-station/door-candidate': [26, 27]}.get(cid, [])
        for member in selected: cases.append((cid + '/member-' + str(member), {s: load(p, member) for s, p in [('reference', source[cid]), ('previous', previous), ('profile', candidate)]}))
        if cid == energy['id']:
            data = {}
            for s, path in [('reference', source[cid]), ('profile', candidate)]:
                g = load(path); p = g.reshape(-1, 3); t = np.arange(len(p)).reshape(-1, 3)
                q, f, _, _ = clip_below(p * 1000, t, np.zeros(len(t), dtype=np.int64), axis=0, height_mm=0)
                data[s] = q[f] / 1000
            cases.append(('energy-cutaway', data))
    raster = module('raster', ROOT / 'benchmarks/2026-10-17-base-passes/validate_render.py').raster; metric = module('metric', ROOT / 'benchmarks/2026-10-17-base-housing-aggressive/review.py').metric
    views = [('oblique', (1, .7, 1.5)), ('reverse', (-1, .7, -1.5)), ('top', (0, 1, .000001)), ('front', (0, .000001, 1)), ('back', (0, .000001, -1)), ('bottom', (0, -1, .000001)), ('side', (1, .000001, 0))]; entries = []; rotation = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'; subprocess.run([shutil.which('clang++'), '-O3', str(ROOT / 'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'), '-o', str(helper)], check=True)
        for cid, data in cases:
            data = {s: g @ rotation.T for s, g in data.items()}; folder = out / 'review' / cid; folder.mkdir(parents=True, exist_ok=True); checks = []
            for name, view in views:
                frames = {s: raster(g, np.tile([.45, .65, .80], (len(g), 1)), data['reference'], view, helper, tmp, folder / (s + '-' + name + '.png')) for s, g in data.items()}
                sheet = Image.new('RGB', (600 * len(frames), 600))
                for j, image in enumerate(frames.values()): sheet.paste(Image.fromarray(image).resize((600, 600), Image.Resampling.LANCZOS), (600 * j, 0))
                sheet.save(folder / (name + '.webp'), lossless=True)
                checks.extend({'view': name, 'stage': s, **metric(frames['reference'], image)} for s, image in frames.items() if s != 'reference')
            entries.append({'id': cid, 'stages': list(data), 'triangles': {s: len(g) for s, g in data.items()}, 'images': str(folder.relative_to(out)), 'views': checks}); print('reviewed', cid, flush=True)
    (out / 'review.json').write_text(json.dumps({'entries': entries, 'energy_summary_sha256': digest(out / 'energy-summary.json'), 'panels_summary_sha256': digest(out / 'panels-summary.json'), 'producer_sha256': digest(__file__), 'scope': 'Seven matched 1200-square two-sided flat views per scope, exported GLBs in source pose. Cutaway clips both models at source X=0 without adding cut faces. Neutral collision colors; no renderer/scoring/moving-pose validation.'}, indent=2) + '\n')


if __name__ == '__main__': main()
