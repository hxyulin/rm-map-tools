# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Independent payload/count checks and finite-view red/green mask comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
from PIL import Image
from gltf_scene import accessor, read_glb, scene_nodes
from simplify_package import scene_triangles


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def masks(image):
    r, g, b = image[:, :, 0], image[:, :, 1], image[:, :, 2]
    return {'red': (r > 150) & (g < 100) & (b < 100),
            'green': (g > 130) & (r < 120) & (b < 120)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-feature-investigation')
    parser.add_argument('--package', type=Path, default=ROOT.parent / 'rm-simulator/field-2027')
    args = parser.parse_args()
    out = args.out.resolve()
    report = json.loads((out / 'review.json').read_text())
    copies = {}
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = args.package / relative
        for name, row in json.loads(manifest.read_text())['assets'].items():
            copies[name] = max(1, len(row['placements_in_source_arena_frame']))
            for role in ('visual', 'collision'):
                if digest(manifest.parent / row[role]) != row[role + '_sha256']:
                    raise ValueError('runtime source mutated')
    checked = {}
    for level in report['levels']:
        total = 0
        for name, row in level['files'].items():
            path = local(row['path'])
            if digest(path) != row['sha256']:
                raise ValueError('candidate changed after rendering')
            if row['sha256'] not in checked:
                doc, blob = read_glb(path)
                live = {doc['nodes'][i]['mesh'] for i, _, _ in scene_nodes(doc) if 'mesh' in doc['nodes'][i]}
                for mi in live:
                    for prim in doc['meshes'][mi]['primitives']:
                        n = doc['accessors'][prim['attributes']['POSITION']]['count']
                        for a in prim['attributes'].values():
                            values = accessor(doc, blob, a)
                            if len(values) != n or not np.isfinite(values).all():
                                raise ValueError('nonfinite or mismatched attributes: ' + str(path))
                        ix = accessor(doc, blob, prim['indices']) if 'indices' in prim else np.arange(n)
                        if len(ix) % 3 or (len(ix) and (ix.min() < 0 or ix.max() >= n)):
                            raise ValueError('invalid written triangle indices')
                checked[row['sha256']] = scene_triangles(doc)
            count = checked[row['sha256']] * copies[name]
            if count != row['triangles']:
                raise ValueError('written triangle count mismatch')
            total += count
        if total != level['triangles']:
            raise ValueError('level total mismatch')
    index = {(v['stage'], v['group'], v['view']): v for v in report['views']}
    if len(index) != len(report['levels']) * 56:
        raise ValueError('incomplete image matrix')
    roles = {level['id']: level['role'] for level in report['levels']}
    baselines = {level['role']: level['id'] for level in report['levels'] if level.get('baseline')}
    baseline_masks = {}
    rows = []
    for row in report['views']:
        path = out / row['image']
        image = np.asarray(Image.open(path).convert('RGB'))
        if image.shape != (1200, 1200, 3):
            raise ValueError('wrong image dimensions')
        baseline_id = baselines[roles[row['stage']]]
        key = (baseline_id, row['group'], row['view'])
        if key not in baseline_masks:
            base = index[key]
            baseline_masks[key] = masks(np.asarray(Image.open(out / base['image']).convert('RGB')))
        reference = baseline_masks[key]
        candidate = masks(image)
        rows.append({**{k: row[k] for k in ('stage', 'group', 'view')},
                     'red_mask_difference_pixels': int(np.count_nonzero(reference['red'] ^ candidate['red'])),
                     'green_mask_difference_pixels': int(np.count_nonzero(reference['green'] ^ candidate['green'])),
                     'image_sha256': digest(path)})
    result = {'verified_unique_geometry_hashes': len(checked), 'verified_views': len(rows),
              'runtime_input_glbs_unchanged': 12, 'views': rows,
              'scope': 'Written payload and triangle checks; thresholded red/green occupancy at seven rest-pose views, not full optical appearance, continuous geometry, animation or collision approval.'}
    (out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Verified', len(checked), 'geometry hashes and', len(rows), 'matched render entries; runtime inputs unchanged.')


if __name__ == '__main__':
    main()
