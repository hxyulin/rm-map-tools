#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare approved, original Low and repaired Low in seven matched views."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image
from plan_cad_lods import digest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-low-repair')
    a = ap.parse_args(); out = a.out.resolve()
    scene = module('scene', 'benchmarks/2026-10-17-composed-pipeline/review.py')
    raster = module('raster', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
    metric = module('metric', 'benchmarks/2026-10-17-base-housing-aggressive/review.py').metric
    paths = {'approved': ROOT / 'out/rmuc2027-equipment-shells/candidate-field.glb',
             'low': ROOT / 'out/rmuc2027-ultra-lod/low-field.glb',
             'budget': out / 'budget-field.glb', 'tight': out / 'tight-field.glb',
             'sealed': out / 'budget-sealed-field.glb'}
    data = {}; owners = {}
    for stage, path in paths.items(): data[stage], owners[stage] = scene.load_scene(path)
    groups = ['field', 'base', 'outpost', 'dart-station', 'rune', 'technology-core', 'energy-unit', 'resource-area']
    report = {'inputs_sha256': {k: digest(p) for k, p in paths.items()}, 'views': [],
              'scope': '1200px matched source-color/embedded-texture, two-sided diagnostic views. Not runtime PBR, continuous surface, animation or collision verification.'}
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'
        subprocess.run([shutil.which('clang++'), '-O3', '-std=c++17', str(ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'), '-o', str(helper)], check=True)
        for group in groups:
            if group == 'field': selected = data
            else:
                first = next(v for v in owners['approved'].values() if v['component_id'].startswith(group + '/'))
                g = data['approved'][0][data['approved'][4] == first['index']]
                anchor = (g.min((0, 1)) + g.max((0, 1))) / 2
                selected = {s: scene.select(d, owners[s], group, anchor) for s, d in data.items()}
            folder = out / 'review' / group; folder.mkdir(parents=True, exist_ok=True)
            views = [('oblique', (1, 1.2 if group == 'field' else .5, 1)), ('reverse', (-1, 1.2 if group == 'field' else .5, -1)), ('top', (0, 1, .000001)), ('front', (0, .000001, 1)), ('back', (0, .000001, -1)), ('side', (1, .000001, 0)), ('bottom', (0, -1, .000001))]
            for name, view in views:
                reference = None
                for stage, d in selected.items():
                    image = raster(d, selected['approved'][0], view, helper, tmp, tmp / 'frame.png')
                    target = folder / (stage + '-' + name + '.webp')
                    Image.fromarray(image).save(target, lossless=True)
                    if reference is None: reference = image
                    report['views'].append({'group': group, 'view': name, 'level': stage, 'triangles': len(d[0]),
                        'image': str(target.relative_to(out)), **({} if stage == 'approved' else metric(reference, image))})
            print('rendered', group, flush=True)
    report['producer_sha256'] = digest(Path(__file__))
    (out / 'review.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
