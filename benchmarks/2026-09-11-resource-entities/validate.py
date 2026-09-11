# SPDX-License-Identifier: MIT OR Apache-2.0
"""Check complete triangle/material conservation after entity extraction."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, mesh_instances


def triangles(path, offset=(0, 0, 0)):
    doc, binary = read_glb(path)
    records = Counter()
    for _, _, points, faces, material in mesh_instances(doc, binary):
        xyz = np.round((points + offset)[faces], 10)
        # Keep winding/order and material, including duplicate triangles.
        records.update((material, tuple(t.ravel())) for t in xyz)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args()
    rules = json.loads((args.after / 'entity-extraction.json').read_text())
    before = json.loads((args.before / 'manifest.json').read_text())
    after = json.loads((args.after / 'manifest.json').read_text())
    source = rules['asset']
    report = {}
    for kind in ('visual', 'collision'):
        expected = triangles(args.before / before['assets'][source][kind])
        actual = triangles(args.after / after['assets'][source][kind])
        counts = {}
        for entity in rules['entities']:
            entry = after['assets'][entity['id']]
            part = triangles(args.after / entry[kind], entity['origin_m'])
            actual.update(part)
            counts[entity['id']] = part.total()
            for old, new in zip(before['assets'][source]['placements_in_source_arena_frame'], entry['placements_in_source_arena_frame']):
                origin = np.eye(4); origin[:3, 3] = entity['origin_m']
                np.testing.assert_allclose(new['matrix_local_to_arena'], np.asarray(old['matrix_local_to_arena']) @ origin, atol=1e-12)
        assert actual == expected, (kind, (actual - expected).total(), (expected - actual).total())
        report[kind] = {'before': expected.total(), 'after_total': actual.total(),
                        'extracted': counts, 'missing': 0, 'extra': 0,
                        'coordinate_comparison_decimal_places': 10}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
