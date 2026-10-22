# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verify source scopes, protected payloads and sampled retained 1 mm coverage."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from cad_dense_lod import surface_samples
from gltf_scene import accessor, read_glb, scene_nodes
from mesh_quality import distances


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-runtime-opportunities')
    args = parser.parse_args()
    out = args.out.resolve()
    spec = importlib.util.spec_from_file_location('refine', Path(__file__).with_name('refine.py'))
    refine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(refine)
    report = json.loads((out / 'refined.json').read_text())
    results = {}
    for name, row in report['assets'].items():
        role = name.split('/')[1]
        target = out / row['output']
        baseline = out / 'meshes' / (role + '-1mm') / target.name
        if refine.digest(baseline) != row['candidate_sha256'] or refine.digest(target) != row['sha256']:
            raise ValueError('input hash mismatch')
        bd, bb = read_glb(baseline)
        ad, ab = read_glb(target)
        bw = {i: w for i, w, _ in scene_nodes(bd)}
        aw = {i: w for i, w, _ in scene_nodes(ad)}
        assert all(np.array_equal(w, aw[i]) for i, w in bw.items())
        assert ad['materials'] == bd['materials']
        # Images and non-structural primitives are checked by actual payload,
        # independently of accessor compaction or mesh-slot changes.
        for before, after in zip(bd.get('images', []), ad.get('images', [])):
            bv = bd['bufferViews'][before['bufferView']]
            av = ad['bufferViews'][after['bufferView']]
            assert bb[bv.get('byteOffset', 0):bv.get('byteOffset', 0) + bv['byteLength']] == ab[av.get('byteOffset', 0):av.get('byteOffset', 0) + av['byteLength']]
        protected = 0
        for i, node in enumerate(bd['nodes']):
            if 'mesh' not in node:
                continue
            for prim in bd['meshes'][node['mesh']]['primitives']:
                if refine.structural(bd['materials'][prim['material']], prim):
                    continue
                assert 'mesh' in ad['nodes'][i]
                matches = [p for p in ad['meshes'][ad['nodes'][i]['mesh']]['primitives'] if p['material'] == prim['material'] and set(p['attributes']) == set(prim['attributes'])]
                assert any(all(np.array_equal(accessor(bd, bb, a), accessor(ad, ab, p['attributes'][k])) for k, a in prim['attributes'].items()) and
                           np.array_equal(accessor(bd, bb, prim['indices']), accessor(ad, ab, p['indices'])) for p in matches)
                protected += 1
        generated = [i for i in range(len(bd['nodes']), len(ad['nodes'])) if 'mesh' in ad['nodes'][i]]
        assert len(generated) == len(row['groups'])
        maximum = 0.
        samples = 0
        for group, child in zip(row['groups'], generated):
            scope = group['scope_node']
            geometry = []
            material = {k: v for k, v in bd['materials'][group['material']].items() if k not in ('name', 'extras')}
            for i in group['source_nodes']:
                matrix = np.linalg.inv(bw[scope]) @ bw[i]
                for prim in bd['meshes'][bd['nodes'][i]['mesh']]['primitives']:
                    mat = bd['materials'][prim['material']]
                    if not refine.structural(mat, prim) or {k: v for k, v in mat.items() if k not in ('name', 'extras')} != material:
                        continue
                    p = accessor(bd, bb, prim['attributes']['POSITION']).astype(float)
                    t = accessor(bd, bb, prim['indices']).reshape(-1, 3)
                    geometry.append((p @ matrix[:3, :3].T + matrix[:3, 3])[t] * 1000)
            original = np.concatenate(geometry)
            assert len(original) == group['before_triangles']
            prim = ad['meshes'][ad['nodes'][child]['mesh']]['primitives'][0]
            p = accessor(ad, ab, prim['attributes']['POSITION']).astype(float) * 1000
            t = accessor(ad, ab, prim['indices']).reshape(-1, 3)
            points = surface_samples(original.reshape(-1, 3), np.arange(original.size // 3).reshape(-1, 3)).reshape(-1, 3)
            delta = distances(points, p, t)
            worst = float(delta.max(initial=0))
            maximum = max(maximum, worst)
            samples += len(points)
            if worst > 1.2:
                raise ValueError(f'refinement lost accepted 1 mm coverage: {name} {group["scope_name"]}: {worst} mm')
        results[name] = {'maximum_sampled_baseline_to_refined_mm': maximum,
                          'samples': samples, 'protected_primitives_verified': protected,
                          'original_node_frames_verified': len(bw), 'sha256': refine.digest(target)}
        print(name, 'max retained-surface distance', maximum, 'mm,', protected, 'protected primitives', flush=True)
    (out / 'refined-verification.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
