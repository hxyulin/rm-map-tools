#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render the assembled source geometry in neutral and articulated poses."""
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
from gltf_scene import mesh_instances, read_glb


def load(path):
    document, binary = read_glb(path)
    geometry, colors = [], []
    for ni, pi, p, t, mat in mesh_instances(document, binary):
        rgb = np.array(document['materials'][mat]['pbrMetallicRoughness']['baseColorFactor'][:3])
        # glTF factors are linear; the diagnostic raster writes sRGB pixels.
        rgb = np.where(rgb <= .0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - .055)
        geometry.append(p[t]);colors.extend([rgb] * len(t))
    return np.concatenate(geometry), np.array(colors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--poses',nargs='+',default=['neutral','aimed','depressed'])
    args = parser.parse_args()
    folder = args.package;out = folder / 'review';out.mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location('robot_raster', ROOT / 'benchmarks/2026-10-17-base-passes/validate_render.py')
    raster = importlib.util.module_from_spec(spec);spec.loader.exec_module(raster)
    cases = {name: load(folder / (name + '.glb')) for name in args.poses}
    reference = np.concatenate([p for p, c in cases.values()])
    stats = {}
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp);helper = temp / 'raster'
        subprocess.run(['clang++', '-O3', str(ROOT / 'benchmarks/2026-10-17-base-analysis/visibility-raster.cpp'), '-o', str(helper)], check=True)
        for name, (p, colors) in cases.items():
            stats[name] = {'bounds_gltf_m': [p.min((0, 1)).tolist(), p.max((0, 1)).tolist()],
                           'dimensions_m': np.ptp(p.reshape(-1, 3), axis=0).tolist(), 'triangles': len(p)}
            for view, direction in [('oblique', (1, .65, 1.5)), ('rear', (-1, .65, -1.5)),
                                    ('side', (1, .1, .00001)), ('top', (.00001, 1, 0))]:
                raster.raster(p, colors, reference, direction, helper, temp, out / (name + '-' + view + '.png'))
            print(name, stats[name], flush=True)
    (out / 'measurements.json').write_text(json.dumps(stats, indent=2) + '\n')


if __name__ == '__main__':
    main()
