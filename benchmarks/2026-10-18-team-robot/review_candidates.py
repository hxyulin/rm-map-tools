#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render complete candidate robots without inferring joints or collision geometry."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, mesh_instances


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--recipe', type=Path, default=Path(__file__).with_name('candidates.json'))
    parser.add_argument('--raw', action='store_true', help='Inspect the original cooked input, including CAD reference geometry.')
    parser.add_argument('--neutral', action='store_true', help='Use lighter unpainted surfaces for geometry inspection only.')
    parser.add_argument('source_id')
    args = parser.parse_args()
    source = json.loads(args.recipe.read_text())['sources'][args.source_id]
    folder = args.sources / (source['source_model_id'] + '-pilot')
    document, binary = read_glb(folder / 'low.glb' if args.raw else folder / 'package/model.glb')
    triangles, colors = [], []
    fallback = [.55, .57, .60] if args.neutral else [.095, .10, .11]
    for ni, pi, points, faces, material in mesh_instances(document, binary):
        mat = document['materials'][material]
        rgb = np.asarray(mat.get('extras', {}).get('step_colour_srgb') or fallback)
        if np.array_equal(rgb, [.7922, .8196, .9333]):
            rgb = np.array(fallback)
        triangles.append(points[faces])
        colors.extend([rgb] * len(faces))
    points, colors = np.concatenate(triangles), np.array(colors)
    # An explicit recipe frame, never guessed from the model's aspect ratio.
    rotation = np.asarray(source['review_rotation'])
    assert np.allclose(rotation @ rotation.T, np.eye(3)) and np.linalg.det(rotation) > .999
    if args.raw:
        points = points @ rotation.T
        low = points.min((0, 1));high = points.max((0, 1))
        points -= np.array([(low[0] + high[0]) / 2, low[1], (low[2] + high[2]) / 2])
        reference = points
    else:
        # Match the raw source framing so helper removal never changes the
        # camera, zoom or centering in a before/after comparison.
        raw = [p[t] @ rotation.T for ni, pi, p, t, m in mesh_instances(*read_glb(folder / 'low.glb'))]
        reference = np.concatenate(raw)
        low = reference.min((0, 1));high = reference.max((0, 1))
        reference -= np.array([(low[0] + high[0]) / 2, low[1], (low[2] + high[2]) / 2])
    out = folder / ('review-raw' if args.raw else 'review');out.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location('candidate_raster', ROOT / 'benchmarks/2026-10-17-base-passes/validate_render.py')
    raster = importlib.util.module_from_spec(spec);spec.loader.exec_module(raster)
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp);helper = temp / 'raster'
        subprocess.run(['clang++', '-O3', str(ROOT / 'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'), '-o', str(helper)], check=True)
        for view, direction in [('oblique', (1, .65, 1.5)), ('rear', (-1, .65, -1.5)),
                                ('side', (1, .1, .00001)), ('top', (.00001, 1, 0))]:
            raster.raster(points, colors, reference, direction, helper, temp, out / (('neutral-' if args.neutral else '') + view + '.png'))
    stats = {'dimensions_gltf_m': np.ptp(points.reshape(-1, 3), axis=0).tolist(),
             'triangles': len(points), 'material_policy': ('Neutral geometry diagnostic' if args.neutral else 'Graphite for explicit fallback and pale CAD tint; other source colors preserved.'),
             'source_id': args.source_id, 'credit': source['credit'],
             'scope': ('Raw source with reference geometry.' if args.raw else 'Physical source candidate with reviewed reference geometry excluded.') + ' No fitted gameplay, suspension or articulation.'}
    (out / ('neutral-measurements.json' if args.neutral else 'measurements.json')).write_text(json.dumps(stats, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
