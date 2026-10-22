# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Record compact counts and checked provenance for the refined inspection set."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import numpy as np
import shapely
from gltf_scene import read_glb, scene_nodes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stats(path):
    doc, _ = read_glb(path)
    uses = [doc['nodes'][i]['mesh'] for i, _, _ in scene_nodes(doc) if 'mesh' in doc['nodes'][i]]
    attrs = {p['attributes']['POSITION'] for mi in set(uses) for p in doc['meshes'][mi]['primitives']}
    return {'bytes': path.stat().st_size,
            'stored_vertices': sum(doc['accessors'][a]['count'] for a in attrs),
            'placed_primitives': sum(len(doc['meshes'][mi]['primitives']) for mi in uses)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-runtime-opportunities')
    args = parser.parse_args()
    out = args.out.resolve()
    report = json.loads((out / 'refined.json').read_text())
    verification = json.loads((out / 'refined-verification.json').read_text())
    for relative, h in report['producer_sha256'].items():
        assert digest(ROOT / relative) == h
    compact = {k: v for k, v in report.items() if k != 'assets'}
    compact.update(environment={'numpy': np.__version__, 'shapely': shapely.__version__, 'geos': shapely.geos_version_string},
                   verification=verification, totals={}, assets={}, recorder_sha256=digest(Path(__file__)))
    for role in ('visual', 'collision'):
        totals = {prefix + '_' + key: 0 for prefix in ('before', 'after') for key in
                  ('triangles', 'bytes', 'stored_vertices', 'placed_primitives')}
        totals['panels'] = 0
        for name, row in report['assets'].items():
            if not name.endswith('/' + role):
                continue
            target = out / row['output']
            baseline = out / 'meshes' / (role + '-1mm') / target.name
            assert digest(target) == row['sha256'] == verification[name]['sha256']
            assert digest(baseline) == row['candidate_sha256']
            for prefix, path in (('before', baseline), ('after', target)):
                totals[prefix + '_triangles'] += row[prefix] * row['placements']
                for key, value in stats(path).items():
                    totals[prefix + '_' + key] += value * (row['placements'] if key == 'placed_primitives' else 1)
            panels = [p for g in row['groups'] for p in g['panels']]
            totals['panels'] += len(panels)
            compact['assets'][name] = {k: v for k, v in row.items() if k != 'groups'}
            compact['assets'][name].update(consolidated_material_groups=len(row['groups']), panels=len(panels),
                maximum_source_plane_distance_mm=max((p['maximum_source_plane_distance_mm'] for p in panels), default=0),
                maximum_projected_boundary_distance_mm=max((p['projected_boundary_distance_mm'] for p in panels), default=0),
                maximum_triangulation_area_difference_mm2=max((p['triangulation_symmetric_difference_mm2'] for p in panels), default=0))
        compact['totals'][role] = totals
    (out / 'refined-totals.json').write_text(json.dumps(compact['totals'], indent=2) + '\n')
    Path(__file__).with_name('refinement-results.json').write_text(json.dumps(compact, indent=2) + '\n')
    print(json.dumps(compact['totals'], indent=2))


if __name__ == '__main__':
    main()
