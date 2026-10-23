# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compare whole-file shape alternatives after reapplying compact-detail policy.

Select one verified result per asset/role; savings from overlapping trials are
never added. Geometry remains an uninstalled inspection candidate.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb
from simplify_package import scene_triangles


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def local(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=Path(__file__).with_name('plan.json'))
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-feature-investigation')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads(args.plan.read_text())
    plan['levels'] = [l for l in plan['levels'] if l.get('policy') != 'combined']
    detail = module('feature_detail_policy', 'benchmarks/2026-10-23-detail-trial/run.py')
    refined = json.loads((ROOT / 'out/rmuc2027-runtime-opportunities/refined.json').read_text())
    assets = {}
    package = local(plan.get('package', '../rm-simulator/field-2027'))
    for relative in ('manifest.json', 'equipment/manifest.json'):
        for name, asset in json.loads((package / relative).read_text())['assets'].items():
            assets[name] = asset
    report = {'assets': {}, 'scope': 'One shape alternative per whole GLB, then explicit backed-detail omission under17mm. Each option is rechecked; no addition of overlapping savings. Inspection only.'}
    for role in ('visual', 'collision'):
        files = {}
        for name, asset in assets.items():
            copies = max(1, len(asset['placements_in_source_arena_frame']))
            baseline_record = refined['assets'][name + '/' + role]
            baseline = ROOT / 'out/rmuc2027-runtime-opportunities' / baseline_record['output']
            options = [('baseline', baseline, baseline_record['sha256'])]
            for level in plan['levels']:
                if level['role'] != role or not level.get('shape_trial') or name not in level.get('files', {}):
                    continue
                entry = level['files'][name]
                options.append((level['id'], local(entry['path']), entry['sha256']))
            rows = []
            seen = set()
            for label, source, sha in options:
                if sha in seen:
                    continue
                seen.add(sha)
                if detail.digest(source) != sha:
                    raise ValueError('primary shape input changed')
                doc, blob = read_glb(source)
                pieces, boxes = detail.prepare(doc, blob)
                target = out / 'combined-17mm' / label / role / source.name
                row = detail.trial(source, target, 17, copies, pieces, boxes, baseline_record['groups'])
                if row is None:
                    path, output_hash = source, sha
                    count = scene_triangles(doc) * copies
                else:
                    path, output_hash = target, row['output_sha256']
                    count = row['after']['placed_triangles']
                rows.append({'primary': label, 'primary_path': str(source), 'primary_sha256': sha,
                             'output': str(path), 'output_sha256': output_hash,
                             'placed_triangles': count, 'detail_selection': row})
                if detail.digest(source) != sha:
                    raise ValueError('primary shape input mutated')
            best = min(rows, key=lambda row: row['placed_triangles'])
            report['assets'][name + '/' + role] = {'baseline': baseline_record['after'] * copies,
                                                   'selected_primary': best['primary'],
                                                   'after': best['placed_triangles'], 'options': rows}
            files[name] = {'path': str(Path(best['output']).relative_to(ROOT)), 'sha256': best['output_sha256']}
            print(name, role, 'selected', best['primary'], baseline_record['after'] * copies,
                  '->', best['placed_triangles'], flush=True)
        plan['levels'].append({'id': 'combined-' + role, 'role': role, 'policy': 'combined',
            'policy_label': 'Combined feature trial', 'label': 'Combined feature trial', 'preferred': True,
            'note': 'Chooses one housing/curve alternative per asset, then re-evaluates deletion of neutral backed detail under17mm. Overlapping savings are not added. Selected shapes and their deliberate local losses are recorded in the ledger. Chromatic/UV/emissive surfaces and their 8mm neighborhoods are excluded from detail omission, but occlusion can change; motion/contact remain unapproved.',
            'files': files})
    (out / 'combined.json').write_text(json.dumps(report, indent=2) + '\n')
    args.plan.write_text(json.dumps(plan, indent=2) + '\n')


if __name__ == '__main__':
    main()
