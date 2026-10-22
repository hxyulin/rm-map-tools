# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measure further reductions after merging, restarting lossy trials at source.

Does not export or install meshes. Sampled checks are not a continuous bound.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
import meshoptimizer as mo
import numpy as np
from cad_dense_lod import surface_samples
from cad_planar_panels import rebuild_panels
from gltf_scene import accessor, read_glb, scene_nodes
from mesh_quality import distances
from simplify_package import simplify_mesh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'out/rmuc2027-runtime-opportunities')
    parser.add_argument('--package', type=Path, default=ROOT.parent / 'rm-simulator/field-2027')
    parser.add_argument('--boundary-mm', type=float, default=.05,
                        help='source panel outline allowance; all trials still face the 1.2 mm sampled guard')
    parser.add_argument('--unlock-remainder-borders', action='store_true',
                        help='unlock other CAD borders while keeping reconstructed panel vertices fixed')
    args = parser.parse_args()
    out = args.out.resolve()
    spec = importlib.util.spec_from_file_location('refine', Path(__file__).with_name('refine.py'))
    refine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(refine)
    report = json.loads((out / 'refined.json').read_text())
    sources = {}
    for relative in ('manifest.json', 'equipment/manifest.json'):
        manifest = args.package / relative
        for name, asset in json.loads(manifest.read_text())['assets'].items():
            for role in ('visual', 'collision'):
                sources[name + '/' + role] = manifest.parent / asset[role]
    results = {}
    for name, row in report['assets'].items():
        source = sources[name]
        target = out / row['output']
        if refine.digest(source) != row['source_sha256'] or refine.digest(target) != row['sha256']:
            raise ValueError('input hash mismatch')
        sd, sb = read_glb(source)
        rd, rb = read_glb(target)
        worlds = {i: w for i, w, _ in scene_nodes(sd)}
        children = [i for i in range(len(sd['nodes']), len(rd['nodes'])) if 'mesh' in rd['nodes'][i]]
        assert len(children) == len(row['groups'])
        zero_total = guarded_total = row['after']
        groups = []
        for group, child in zip(row['groups'], children):
            prim = rd['meshes'][rd['nodes'][child]['mesh']]['primitives'][0]
            p = accessor(rd, rb, prim['attributes']['POSITION'])
            t = accessor(rd, rb, prim['indices']).reshape(-1, 3)
            q, inv = np.unique(p, axis=0, return_inverse=True)
            q = np.ascontiguousarray(q.astype(float) - q.astype(float).mean(0), dtype=np.float32)
            ix = np.ascontiguousarray(inv[t].ravel(), dtype=np.uint32)
            dest = np.empty_like(ix)
            count = mo.simplify(dest, ix, q, target_index_count=3, target_error=0,
                                options=mo.SIMPLIFY_ERROR_ABSOLUTE | mo.SIMPLIFY_LOCK_BORDER)
            zero = count // 3 if count else len(t)
            zero_total += zero - len(t)
            material = {k: v for k, v in sd['materials'][group['material']].items() if k not in ('name', 'extras')}
            scope = group['scope_node']
            geometry = []
            for i in group['source_nodes']:
                matrix = np.eye(4) if i == scope else np.linalg.inv(worlds[scope]) @ worlds[i]
                for prim in sd['meshes'][sd['nodes'][i]['mesh']]['primitives']:
                    mat = sd['materials'][prim['material']]
                    if not refine.structural(mat, prim) or {k: v for k, v in mat.items() if k not in ('name', 'extras')} != material:
                        continue
                    p = accessor(sd, sb, prim['attributes']['POSITION']).astype(float)
                    t = accessor(sd, sb, prim['indices']).reshape(-1, 3)
                    if np.linalg.det(matrix[:3, :3]) < 0:
                        t = t[:, ::-1]
                    geometry.append((p @ matrix[:3, :3].T + matrix[:3, 3])[t] * 1000)
            source_g = np.concatenate(geometry)
            assert len(source_g) == group['source_triangles']
            keep, patch, _ = rebuild_panels(source_g, source_g, boundary_tolerance_mm=args.boundary_mm)
            combined = np.concatenate([source_g[keep], patch])
            points = combined.reshape(-1, 3) / 1000
            triangles = np.arange(len(points)).reshape(-1, 3)
            # All reconstructed panel vertices are polygon boundaries. Locking
            # them freezes the cleaned outlines while simplifying the remainder.
            locks = np.arange(len(source_g[keep]) * 3, len(points))
            best = group['after_triangles']
            trials = []
            for metric in (1, .5, .25):
                q, f, error = simplify_mesh(points, triangles, metric / 1000,
                                            lock_borders=not args.unlock_remainder_borders,
                                            locked_vertex_indices=locks)
                trial = {'metric_mm': metric, 'triangles': len(f), 'reported_metric_mm': error * 1000}
                trials.append(trial)
                if len(f) >= best:
                    # Lower error cannot improve this monotonic selection's
                    # cost sufficiently to justify a full sampled comparison.
                    continue
                source_p = source_g.reshape(-1, 3)
                source_t = np.arange(len(source_p)).reshape(-1, 3)
                forward = distances(surface_samples(source_p, source_t).reshape(-1, 3), q * 1000, f)
                reverse = distances(surface_samples(q * 1000, f).reshape(-1, 3), source_p, source_t)
                maximum = float(max(forward.max(initial=0), reverse.max(initial=0)))
                trial['maximum_bidirectional_sampled_mm'] = maximum
                trial['samples'] = len(forward) + len(reverse)
                trial['accepted_for_count'] = maximum <= 1.2
                if maximum <= 1.2:
                    best = len(f)
            guarded_total += best - group['after_triangles']
            groups.append({'scope': group['scope_name'], 'before': group['after_triangles'],
                           'zero_metric': zero, 'guarded_source_trial': best, 'trials': trials})
        copies = row['placements']
        results[name] = {'source_sha256': row['source_sha256'], 'refined_sha256': row['sha256'],
                         'before': row['after'] * copies, 'zero_metric': zero_total * copies,
                         'guarded_source_trial': guarded_total * copies, 'placements': copies, 'groups': groups}
        print(name, results[name]['before'], '-> zero', results[name]['zero_metric'],
              '/ source guarded', results[name]['guarded_source_trial'], flush=True)
        assert refine.digest(source) == row['source_sha256'] and refine.digest(target) == row['sha256']
    totals = {}
    for role in ('visual', 'collision'):
        totals[role] = {key: sum(r[key] for name, r in results.items() if name.endswith('/' + role)) for key in
                        ('before', 'zero_metric', 'guarded_source_trial')}
    result = {'assets': results, 'totals': totals, 'boundary_tolerance_mm': args.boundary_mm,
              'lock_remainder_borders': not args.unlock_remainder_borders,
              'producer_sha256': refine.digest(Path(__file__)),
              'scope': 'Read-only counts. Zero metric does not certify equality. Guarded trials start at original grouped source, pin rebuilt panel vertices, optionally lock other open boundaries, preserve component survival, and check seven samples per triangle both ways at 1.2 mm. Failed/non-cheaper trials retain the reviewed refinement. No export, global topology/optical approval or runtime timing.'}
    filename = 'merged-probe.json' if args.boundary_mm == .05 else f'merged-probe-outline-{args.boundary_mm:g}mm.json'
    if args.unlock_remainder_borders:
        filename = filename.replace('.json', '-open-remainder.json')
    (out / filename).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(totals), flush=True)


if __name__ == '__main__':
    main()
