# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Add refined 1 mm renders to the original comparison palette."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-runtime-opportunities')
    parser.add_argument('--package', type=Path, default=ROOT.parent / 'rm-simulator/field-2027')
    args = parser.parse_args()
    out = args.out.resolve()
    render = module('runtime_render', 'benchmarks/2026-10-23-runtime-opportunities/render.py')
    raster = render.module('raster_panels', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
    report = json.loads((out / 'renders.json').read_text())
    refined = json.loads((out / 'refined.json').read_text())
    paths = {'visual-current': [], 'visual-refined-1mm': [], 'collision-refined-1mm': []}
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = args.package / relative
        for name, asset in json.loads(manifest.read_text())['assets'].items():
            placements = asset['placements_in_source_arena_frame']
            paths['visual-current'].append((name, manifest.parent / asset['visual'], placements))
            for role in ('visual', 'collision'):
                r = refined['assets'][name + '/' + role]
                path = out / r['output']
                if render.digest(path) != r['sha256']:
                    raise ValueError('refined input hash mismatch')
                paths[role + '-refined-1mm'].append((name, path, placements))
    data, owners = {}, {}
    for stage, inputs in paths.items():
        data[stage], owners[stage] = render.load_stage(inputs)
        if stage != 'visual-current':
            report['stages'][stage] = {'triangles': len(data[stage][0]),
                                        'files': {str(p): render.digest(p) for _, p, _ in inputs}}
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        helper = tmp / 'raster'
        subprocess.run([shutil.which('clang++') or shutil.which('g++'), '-O3', '-std=c++17',
                        str(ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'), '-o', str(helper)], check=True)
        for group in ('field', 'tech-core', 'rune', 'dart-station', 'outpost', 'base', 'resource-area', 'energy-unit'):
            anchor = None
            if group in ('dart-station', 'resource-area', 'energy-unit'):
                first = next(v for v in owners['visual-current'].values() if v['component_id'].startswith(group + '/'))
                g = data['visual-current'][0][data['visual-current'][4] == first['index']]
                anchor = (g.min((0, 1)) + g.max((0, 1))) / 2
            selected = {s: render.select_group(d, owners[s], group, anchor) for s, d in data.items()}
            views = [('oblique', (1, 1.2 if group == 'field' else .5, 1)),
                     ('reverse', (-1, 1.2 if group == 'field' else .5, -1)),
                     ('top', (0, 1, .000001)), ('front', (0, .000001, 1)),
                     ('back', (0, .000001, -1)), ('side', (1, .000001, 0)),
                     ('bottom', (0, -1, .000001))]
            folder = out / 'renders' / group
            for view_name, direction in views:
                for stage in ('visual-refined-1mm', 'collision-refined-1mm'):
                    d = selected[stage]
                    target = folder / (stage + '-' + view_name + '.webp')
                    image = raster(d, selected['visual-current'][0], direction, helper, tmp, tmp / 'frame.png')
                    render.Image.fromarray(image).save(target, lossless=True)
                    report['views'].append({'group': group, 'view': view_name, 'stage': stage,
                                            'triangles': len(d[0]), 'image': str(target.relative_to(out))})
            print('rendered refined', group, flush=True)
    report['refinement_sha256'] = render.digest(out / 'refined.json')
    (out / 'refined-renders.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
