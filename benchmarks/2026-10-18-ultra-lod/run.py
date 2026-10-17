#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Export and render a deliberately lossy full-arena visual LOD palette."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image
from cad_experimental_lod import export_trial
from plan_cad_lods import digest


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-ultra-lod')
    ap.add_argument('--reuse', action='store_true', help='reuse previously exported trials')
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'out/rmuc2027-equipment-shells/candidate-field.glb'
    source_hash = digest(source)
    exporter_hash = digest(ROOT / 'python/cad_experimental_lod.py')
    specs = [('approved', 1), ('coarse', .35), ('low', .1), ('ultra', .02), ('extreme', .005)]
    paths = {'approved': source}; report = {'source_sha256': source_hash, 'levels': [], 'views': [],
        'scope': 'Visual experiments only. No surface deviation, optical fidelity, opening clearance, collision or motion certification. Original transforms, shared mesh references, material tables, embedded artwork and selected source attributes retained.'}
    baseline = json.loads((source.parent / 'summary.json').read_text())['totals']
    report['levels'].append({'level': 'approved', 'target_ratio': 1, 'placed_triangles': baseline['visual_placed'], 'stored_triangles': baseline['stored_triangles'], 'bytes': source.stat().st_size})
    for name, ratio in specs[1:]:
        target = out / (name + '-field.glb'); paths[name] = target
        if a.reuse and target.exists():
            row = json.loads((out / (name + '.json')).read_text())
            if row['source_sha256'] != source_hash or row['sha256'] != digest(target) or row['target_ratio'] != ratio or row.get('exporter_sha256') != exporter_hash: raise ValueError('stale trial; run without --reuse')
        else:
            row = export_trial(source, target, ratio)
            row.update(level=name, source_sha256=source_hash, sha256=digest(target), exporter_sha256=exporter_hash)
            (out / (name + '.json')).write_text(json.dumps(row, indent=2) + '\n')
        report['levels'].append({k: v for k, v in row.items() if k != 'primitives'})
        print(name, row['placed_triangles'], 'placed /', row['stored_triangles'], 'stored', flush=True)
    scene = module('scene', 'benchmarks/2026-10-17-composed-pipeline/review.py')
    raster = module('raster', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
    metric = module('metric', 'benchmarks/2026-10-17-base-housing-aggressive/review.py').metric
    data = {}; owners = {}
    for name, path in paths.items(): data[name], owners[name] = scene.load_scene(path)
    groups = ['field', 'base', 'outpost', 'dart-station', 'rune', 'technology-core', 'energy-unit', 'resource-area']
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
            views = [('oblique', (1, 1.2 if group == 'field' else .5, 1)), ('reverse', (-1, 1.2 if group == 'field' else .5, -1)), ('top', (0, 1, .000001))]
            for name, view in views:
                reference = None
                for stage, d in selected.items():
                    png = tmp / 'frame.png'
                    image = raster(d, selected['approved'][0], view, helper, tmp, png)
                    Image.fromarray(image).save(folder / (stage + '-' + name + '.webp'), lossless=True)
                    if reference is None: reference = image
                    report['views'].append({'group': group, 'view': name, 'level': stage,
                        'triangles': len(d[0]), 'image': str((folder / (stage + '-' + name + '.webp')).relative_to(out)),
                        **({} if stage == 'approved' else metric(reference, image))})
            print('rendered', group, flush=True)
    if digest(source) != source_hash: raise ValueError('source changed')
    report['producer_sha256'] = {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), ROOT / 'python/cad_experimental_lod.py']}
    (out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
