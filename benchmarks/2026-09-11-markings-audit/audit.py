# SPDX-License-Identifier: MIT OR Apache-2.0
"""Read-only inventory of the deployed package and reviewed artwork selections.

Selections apply only to the checksum-pinned package in report.json. They are
an inspection result, never an export policy or permission to remove collision.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import mesh_instances, read_glb, scene_nodes


def category(asset, node, primitive, material, thickness):
    if asset == 'arena-static':
        if material == 0 or (node in (384, 385) and primitive == 1):
            return 'floor lettering and white markings'
        if material in (1, 4) and thickness <= 6:
            return 'coloured boundary candidates'
    if asset == 'centre-platform' and node >= 2:
        return 'centre lettering'
    if asset == 'base' and (node, primitive) == (2, 5):
        return 'base logo and wordmark'
    if asset == 'dart-station' and (node, primitive) == (192, 3):
        return 'dart gate logo'
    if asset == 'rune' and node in (17, 19) and primitive == 1:
        return 'rune R artwork'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    pinned = json.loads(Path(__file__).with_name('baseline.json').read_text())['assets']
    rows, assets, groups = [], {}, {}
    for manifest_path in (args.package / 'manifest.json', args.package / 'equipment/manifest.json'):
        manifest = json.loads(manifest_path.read_text())
        for asset, entry in manifest['assets'].items():
            path = manifest_path.parent / entry['visual']
            if hashlib.sha256(path.read_bytes()).hexdigest() != pinned[asset]['visual_sha256']:
                raise ValueError(f'{asset}: visual changed; review selectors before auditing')
            document, binary = read_glb(path)
            placements = max(1, len(entry['placements_in_source_arena_frame']))
            collision_path = manifest_path.parent / entry['collision']
            if hashlib.sha256(collision_path.read_bytes()).hexdigest() != pinned[asset]['collision_sha256']:
                raise ValueError(f'{asset}: collider changed; review selectors before auditing')
            cd, cb = read_glb(collision_path)
            collision = {}
            for ni, _, _ in scene_nodes(cd):
                n = cd['nodes'][ni]
                if 'mesh' not in n:
                    continue
                for pr in cd['meshes'][n['mesh']]['primitives']:
                    key = (n.get('name'), cd['materials'][pr['material']]['name'])
                    collision.setdefault(key, []).append(cd['accessors'][pr['indices']]['count'] // 3)
            total = 0
            for ni, pi, points, triangles, material in mesh_instances(document, binary):
                centered = points - points.mean(0)
                _, basis = np.linalg.eigh(centered.T @ centered / len(points))
                span = np.ptp(centered @ basis, axis=0) * 1000
                node = document['nodes'][ni]
                matname = document['materials'][material]['name']
                group = category(asset, ni, pi, material, span[0])
                row = dict(asset=asset, file=str(path.resolve()), node=ni,
                           name=node.get('name'), primitive=pi, material=material,
                           triangles=len(triangles), span_mm=span.tolist(), group=group,
                           placements=placements)
                total += len(triangles)
                if group:
                    matches = collision.get((node.get('name'), matname), [])
                    # Do not assume visual and collider triangle indices coincide.
                    if len(matches) > 1:
                        raise ValueError(f'ambiguous collider match: {asset} {ni} {pi}')
                    row['collision_triangles'] = matches[0] if matches else 0
                    g = groups.setdefault(group, dict(asset=asset, sections=0, visual=0, collision_file=0))
                    g['sections'] += 1
                    g['visual'] += len(triangles) * placements
                    g['collision_file'] += row['collision_triangles'] * placements
                rows.append(row)
            assets[asset] = dict(placements=placements, visual_per_instance=total,
                                 visual_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                 collision_sha256=hashlib.sha256(collision_path.read_bytes()).hexdigest())
    report = dict(package=str(args.package.resolve()), assets=assets, groups=groups,
                  visual_total=sum(a['placements']*a['visual_per_instance'] for a in assets.values()),
                  selected_visual=sum(g['visual'] for g in groups.values()),
                  selected_collision_file=sum(g['collision_file'] for g in groups.values()),
                  sections=len(rows), rows=rows)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','assets')}, indent=2))


if __name__ == '__main__':
    main()
