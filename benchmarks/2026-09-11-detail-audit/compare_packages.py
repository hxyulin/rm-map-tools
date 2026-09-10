# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compare placed scene-reachable triangles in two deployed packages."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def triangles(path, static_only=False):
    data = path.read_bytes()
    g = json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])
    def walk(i, inside=False):
        node = g['nodes'][i]
        inside = inside or node.get('name') == 'static'
        n = 0
        if 'mesh' in node and (not static_only or inside):
            for p in g['meshes'][node['mesh']]['primitives']:
                if p.get('mode', 4) == 4:
                    n += g['accessors'][p.get('indices', p['attributes']['POSITION'])]['count'] // 3
        return n + sum(walk(c, inside) for c in node.get('children', []))
    return sum(walk(i) for i in g['scenes'][g.get('scene', 0)]['nodes'])


def inspect(root):
    assets = {}
    for mf in ('manifest.json', 'equipment/manifest.json'):
        base = root / Path(mf).parent
        manifest = json.loads((root / mf).read_text())
        for name, a in manifest['assets'].items():
            placed = max(1, len(a.get('placements_in_source_arena_frame', [])))
            visual = base / a['visual']
            collision = base / (a['collision'] if a.get('collision_method') == 'source-tessellation-v1' else a['visual'])
            assets[name] = {'instances': placed, 'visual': placed * triangles(visual),
                            'static_collision_input': placed * triangles(collision, name in ('rune', 'outpost')),
                            'visual_sha256': hashlib.sha256(visual.read_bytes()).hexdigest(),
                            'collision_sha256': hashlib.sha256(collision.read_bytes()).hexdigest()}
    return {'assets': assets, 'visual': sum(a['visual'] for a in assets.values()),
            'static_collision_input': sum(a['static_collision_input'] for a in assets.values())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = {key: inspect(root) for key, root in [('before', args.before), ('after', args.after)]}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    for key, value in result.items():
        print(key, value['visual'], value['static_collision_input'])
