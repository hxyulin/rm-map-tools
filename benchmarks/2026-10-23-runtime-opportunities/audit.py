# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only, unguarded position-only probes of a simulator runtime package.

Counts identify candidates for investigation, never approved meshes or speedups.
No geometry is exported. Zero metric is not proof of exact surface equivalence.
"""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import meshoptimizer as mo
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import accessor, read_glb, scene_nodes


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_asset(path, placements):
    before_hash = digest(path)
    doc, blob = read_glb(path)
    uses = Counter()
    scales = {}
    names = {}
    owners = {}
    components = {}
    for i, world, parent in scene_nodes(doc):
        node = doc['nodes'][i]
        components[i] = node.get('extras', {}).get('component_id') or components.get(parent, 'unclassified')
        if 'mesh' not in node:
            continue
        mi = node['mesh']
        uses[mi] += placements
        owners.setdefault(mi, Counter())[components[i]] += placements
        scales[mi] = max(scales.get(mi, 0), float(np.linalg.svd(world[:3, :3], compute_uv=False).max()))
        if not np.isfinite(scales[mi]) or scales[mi] <= 0:
            raise ValueError('invalid mesh instance scale')
        names.setdefault(mi, node.get('name', str(i)))
    rows = []
    for mi in sorted(uses):
        for pi, prim in enumerate(doc['meshes'][mi]['primitives']):
            if prim.get('mode', 4) != 4 or 'targets' in prim:
                raise ValueError('expected rigid triangle primitive')
            p = accessor(doc, blob, prim['attributes']['POSITION'])
            t = (accessor(doc, blob, prim['indices']) if 'indices' in prim else np.arange(len(p))).reshape(-1, 3)
            # Exact welding, local rebasing and maximum instance scale; no
            # material/primitive/mesh owners are combined by this probe.
            q, inv = np.unique(p, axis=0, return_inverse=True)
            q = np.ascontiguousarray((q.astype(float) - q.astype(float).mean(0)) * scales[mi], dtype=np.float32)
            ix = np.ascontiguousarray(inv[t].ravel(), dtype=np.uint32)
            dest = np.empty_like(ix)
            probes = {}
            for mm in (0, .1, 1, 4):
                error = np.zeros(1, dtype=np.float32)
                count = mo.simplify(dest, ix, q, target_index_count=3,
                                    target_error=mm / 1000,
                                    options=mo.SIMPLIFY_ERROR_ABSOLUTE,
                                    result_error=error)
                if count % 3 or count > len(ix) or (count and dest[:count].max() >= len(q)):
                    raise ValueError('invalid simplifier output')
                # Empty outputs are not a saving: retain the input instead.
                probes[str(mm)] = {'triangles': count // 3 if count else len(t),
                                   'empty_fallback': not bool(count),
                                   'reported_metric_mm': float(error[0]) * 1000}
            rows.append({'mesh': mi, 'primitive': pi, 'node_example': names[mi],
                         'instances': uses[mi], 'owners': dict(owners[mi]), 'triangles': len(t),
                         'attributes': sorted(prim['attributes']), 'probes': probes})
    if digest(path) != before_hash:
        raise ValueError('input changed during audit')
    return {'sha256': before_hash, 'placements': placements,
            'stored_triangles': sum(r['triangles'] for r in rows),
            'placed_triangles': sum(r['triangles'] * r['instances'] for r in rows),
            'placed_primitives': sum(r['instances'] for r in rows),
            'probe_placed_triangles': {str(mm): sum(r['probes'][str(mm)]['triangles'] * r['instances'] for r in rows) for mm in (0, .1, 1, 4)},
            'primitives': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    if args.out.resolve().is_relative_to(package):
        parser.error('audit output must be outside the input package')
    report = {'schema': 1, 'meshoptimizer': importlib.metadata.version('meshoptimizer'),
              'producer_sha256': digest(Path(__file__)),
              'scope': 'Unguarded position-only diagnostic. Ignores attributes, optics, disconnected piece survival, openings and coverage. Zero metric is not exact equivalence. Not exported or approved; no runtime timings.',
              'manifests': {}, 'assets': {}}
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = package / relative
        manifest_hash = digest(manifest)
        data = json.loads(manifest.read_text())
        if data['units'] != 'metres':
            raise ValueError('expected metres')
        report['manifests'][relative] = manifest_hash
        for name, asset in data['assets'].items():
            copies = max(1, len(asset['placements_in_source_arena_frame']))
            for role in ('visual', 'collision'):
                path = manifest.parent / asset[role]
                if digest(path) != asset[role + '_sha256']:
                    raise ValueError(f'manifest hash mismatch: {path}')
                print(f'{name} {role}', flush=True)
                report['assets'][f'{name}/{role}'] = audit_asset(path, copies)
        if digest(manifest) != manifest_hash:
            raise ValueError('manifest changed during audit')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    for name, asset in report['assets'].items():
        print(name, asset['placed_triangles'], asset['probe_placed_triangles'])


if __name__ == '__main__':
    main()
