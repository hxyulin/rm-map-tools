#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render actual road GLBs and monochrome collider candidates in matched views."""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from run import ROOT, module
import numpy as np
from PIL import Image
from gltf_scene import read_glb, mesh_instances
from plan_cad_lods import digest


def load(path, selected_faces=None):
    doc, blob = read_glb(path); geometry = []; colors = []
    rotation = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    for node, pi, p, t, mi in mesh_instances(doc, blob):
        if selected_faces is not None:
            prim = doc['meshes'][doc['nodes'][node]['mesh']]['primitives'][pi]
            keep = np.zeros(len(t), bool)
            for run in prim['extras']['source_native_face_runs']:
                if run['source_face_index'] in selected_faces: keep[run['first_triangle']:run['first_triangle'] + run['triangle_count']] = True
            t = t[keep]
            if not len(t): continue
        color = doc['materials'][mi]['extras']['step_colour_srgb'] or [.6275] * 3
        geometry.append(p[t] @ rotation.T); colors.extend([color] * len(t))
    return np.concatenate(geometry), np.array(colors)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(); out = args.out.resolve(); entries = []
    raster = module('raster', ROOT / 'benchmarks/2026-10-17-base-passes/validate_render.py').raster
    metric = module('metric', ROOT / 'benchmarks/2026-10-17-base-housing-aggressive/review.py').metric
    road = json.loads((out / 'summary.json').read_bytes()); collision = json.loads((out / 'collision-summary.json').read_bytes())
    composition = json.loads((ROOT / 'out/rmuc2027-residual-equipment/composition.json').read_bytes()); by_id = {r['id']: r for r in composition['components']}
    cases = []
    for row in road['components']:
        if not row['id'].startswith('red-'): continue
        folder = out / row['id']; data = {s: load(folder / (s + '.glb')) for s in ['reference', 'sections-16']}
        cases.append((row['id'], 'visual', data))
        if '/shell-' in row['id']:
            cases.append(('road-wave-closeup', 'visual', {s: load(folder / (s + '.glb'), {12, 14, 15}) for s in ['reference', 'sections-16']}))
    for cid in dict.fromkeys(r['id'] for r in collision['components']):
        data = {'reference': load(ROOT / by_id[cid]['candidate_glb'])}
        data.update({s: load(out / cid / (s + '.glb')) for s in ['contact-3mm', 'contact-6mm']})
        data = {s: (g, np.tile([.45, .65, .80], (len(g), 1))) for s, (g, c) in data.items()}
        cases.append((cid, 'collision', data))
    views = [('oblique', (1, .7, 1.5)), ('reverse', (-1, .7, -1.5)), ('top', (0, 1, .000001)), ('front', (0, .000001, 1)), ('back', (0, .000001, -1)), ('bottom', (0, -1, .000001))]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'
        subprocess.run([shutil.which('clang++'), '-O3', str(ROOT / 'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'), '-o', str(helper)], check=True)
        for cid, kind, data in cases:
            folder = out / 'review' / cid; folder.mkdir(parents=True, exist_ok=True); checks = []
            for name, view in views:
                frames = {s: raster(g, c, data['reference'][0], view, helper, tmp, folder / (s + '-' + name + '.png')) for s, (g, c) in data.items()}
                sheet = Image.new('RGB', (600 * len(frames), 600))
                for j, image in enumerate(frames.values()): sheet.paste(Image.fromarray(image).resize((600, 600), Image.Resampling.LANCZOS), (600 * j, 0))
                sheet.save(folder / (name + '.webp'), lossless=True)
                checks.extend({'view': name, 'stage': stage, **metric(frames['reference'], image)} for stage, image in frames.items() if stage != 'reference')
            entries.append({'id': cid, 'kind': kind, 'stages': list(data), 'triangles': {s: len(g) for s, (g, c) in data.items()}, 'images': str(folder.relative_to(out)), 'views': checks})
            print('rendered', cid, flush=True)
    (out / 'review.json').write_text(json.dumps({'entries': entries, 'road_summary_sha256': digest(out / 'summary.json'), 'collision_summary_sha256': digest(out / 'collision-summary.json'),
                                               'producer_sha256': digest(__file__), 'scope': 'Six matched 1200-square orthographic two-sided flat diagnostic views per scope. Collision variants intentionally unpainted. Native pose only, not runtime PBR or moving/scoring validation.'}, indent=2) + '\n')


if __name__ == '__main__': main()
