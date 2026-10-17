#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Find source pieces responsible for visible Low defects in assembled views.

Only requests additional retention relative to Low. This is not an authorization
to delete occluded geometry, nor a proof about unseen cameras or moving poses.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from build import ROOT
from review import module
import numpy as np
from scipy.ndimage import binary_erosion
from cad_component_detail import connected_pieces
from gltf_scene import read_glb, accessor, scene_nodes
from plan_cad_lods import digest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-low-repair')
    ap.add_argument('--candidate', type=Path)
    ap.add_argument('--interior-holes-only', action='store_true')
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'out/rmuc2027-equipment-shells/candidate-field.glb'
    low = a.candidate.resolve() if a.candidate else ROOT / 'out/rmuc2027-ultra-lod/low-field.glb'
    sd, sb = read_glb(source); ld, lb = read_glb(low)
    labels = {}; keys = {}; extents = {}; chromatic = {}
    for mi, mesh in enumerate(sd['meshes']):
        for pi, prim in enumerate(mesh['primitives']):
            p = accessor(sd, sb, prim['attributes']['POSITION']); t = accessor(sd, sb, prim['indices']).reshape(-1, 3)
            lab = connected_pieces(p * 1000, t, selection_grid_mm=.0001)
            labels[mi, pi] = lab; vertex_labels = np.zeros(len(p), int); vertex_labels[t.ravel()] = np.repeat(lab, 3)
            keys[mi, pi] = {tuple(v): int(k) for v, k in zip(p, vertex_labels)}
            mat = sd['materials'][prim['material']]; color = mat.get('extras', {}).get('step_colour_srgb') or [.6] * 3
            for key in np.unique(lab):
                extent = np.ptp(p[t[lab == key]].reshape(-1, 3), axis=0).max() * 1000
                extents[mi, pi, int(key)] = float(extent)
                chromatic[mi, pi, int(key)] = max(color) - min(color) > .15
    def metadata(doc, blob, is_low):
        result = []
        for ni, world, parent in scene_nodes(doc):
            node = doc['nodes'][ni]
            if 'mesh' not in node: continue
            for pi, prim in enumerate(doc['meshes'][node['mesh']]['primitives']):
                mi = node['mesh']; original_pi = pi
                t = accessor(doc, blob, prim['indices']).reshape(-1, 3)
                if is_low:
                    mi = prim['extras']['source_mesh_index']; original_pi = prim['extras']['source_primitive_index']
                    p = accessor(doc, blob, prim['attributes']['POSITION'])
                    lab = np.array([keys[mi, original_pi][tuple(v)] for v in p])
                    result.extend([(mi, original_pi, tuple(sorted(set(map(int, x)))), fi) for fi, x in enumerate(lab[t])])
                else: result.extend([(mi, pi, (int(k),), fi) for fi, k in enumerate(labels[mi, pi])])
        return result
    meta = {'approved': metadata(sd, sb, False), 'low': metadata(ld, lb, True)}
    scene = module('scene', 'benchmarks/2026-10-17-composed-pipeline/review.py')
    raster = module('raster', 'benchmarks/2026-10-17-base-panel-textures/review.py').raster
    data = {}; owners = {}
    for stage, path in [('approved', source), ('low', low)]: data[stage], owners[stage] = scene.load_scene(path)
    selected = set(); records = []; source_triangles = set()
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory); helper = tmp / 'raster'
        subprocess.run([shutil.which('clang++'), '-O3', '-std=c++17', str(ROOT / 'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'), '-o', str(helper)], check=True)
        for group in ['field', 'base', 'outpost', 'dart-station', 'rune', 'technology-core', 'energy-unit', 'resource-area']:
            if group == 'field': parts = data
            else:
                first = next(v for v in owners['approved'].values() if v['component_id'].startswith(group + '/'))
                g = data['approved'][0][data['approved'][4] == first['index']]
                anchor = (g.min((0, 1)) + g.max((0, 1))) / 2
                parts = {s: scene.select(d, owners[s], group, anchor) for s, d in data.items()}
            mappings = {s: np.flatnonzero(np.isin(data[s][4], p[4])) for s, p in parts.items()}
            for name, view in [('oblique', (1, 1.2 if group == 'field' else .5, 1)), ('reverse', (-1, .5, -1)), ('top', (0, 1, .000001)), ('front', (0, .000001, 1)), ('back', (0, .000001, -1)), ('side', (1, .000001, 0)), ('bottom', (0, -1, .000001))]:
                frames = {}; pixels = {}
                for stage, d in parts.items():
                    frames[stage] = raster(d, parts['approved'][0], view, helper, tmp, tmp / 'frame.png')
                    pixels[stage] = np.fromfile(tmp / 'owners.bin', dtype='<i4').reshape(1200, 1200)
                foreground = pixels['approved'] >= 0; current = pixels['low'] >= 0
                # Interior color/occlusion errors, plus silhouette changes. The
                # erosion suppresses one-pixel edge rasterization differences.
                difference = np.max(abs(frames['approved'].astype(int) - frames['low'].astype(int)), axis=2)
                bad = ((difference > 35) & binary_erosion(foreground | current)) | (foreground ^ current)
                if a.interior_holes_only:
                    bad = binary_erosion(foreground, iterations=3) & ~current
                added = set()
                for stage in parts:
                    counts = Counter(); visible = Counter()
                    for triangle, count in zip(*np.unique(pixels[stage][bad], return_counts=True)):
                        if triangle < 0: continue
                        mi, pi, labs, fi = meta[stage][mappings[stage][triangle]]
                        if a.interior_holes_only and stage == 'approved': source_triangles.add((mi, pi, fi))
                        for label in labs: counts[mi, pi, label] += int(count)
                    for triangle, count in zip(*np.unique(pixels[stage], return_counts=True)):
                        if triangle < 0: continue
                        mi, pi, labs, fi = meta[stage][mappings[stage][triangle]]
                        for label in labs: visible[mi, pi, label] += int(count)
                    for key, count in counts.items():
                        if a.interior_holes_only:
                            if count >= 2: added.add(key)
                        else:
                            if extents[key] < 17 and not chromatic[key]: continue
                            if count >= max(2 if chromatic[key] else 8, .005 * visible[key]): added.add(key)
                selected.update(added)
                records.append({'group': group, 'view': name, 'bad_pixels': int(bad.sum()), 'pieces': len(added)})
            print(group, 'selected', len(selected), 'pieces', flush=True)
    report = {'source_sha256': digest(source), 'low_sha256': digest(low),
              'pieces': [list(k) for k in sorted(selected)], 'views': records,
              'producer_sha256': digest(Path(__file__)),
              'scope': 'Seven assembled views request more source-piece fidelity than Low; finite source-pose inspection only. No visibility-based deletion or motion/collision certification.'}
    report['interior_holes_only'] = a.interior_holes_only
    report['source_triangles'] = [list(k) for k in sorted(source_triangles)]
    (out / ('seal-plan.json' if a.interior_holes_only else 'repair-plan.json')).write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__': main()
