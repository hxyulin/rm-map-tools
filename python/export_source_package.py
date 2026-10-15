#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Export an entire source assembly without season-specific equipment grafts.

Source root occurrences partition the full map; repeated products share meshes.
The checksum-pinned configuration supplies names by product ID, avoiding Creo's
duplicate product names. CAD and local GLBs retain source axes; external
placements and the full map use a right-handed Z-up arena frame in metres.
No mechanical motion is inferred from an assembly name or from an older season.

Run with the CAD Python environment:
  export_source_package.py SPLIT INDEX.npz --config rules/sources-2027.json
      --source rmuc2027 --out out/rm2027/packages/rmuc2027
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from export_elements import Package, in_metres, placement_entry, translation
from export_field_package import GlbWriter, sha256
from export_policy import add_arguments, from_arguments
from export_semantics import annotate_package
from export_step_elements import shape_counts, write_assembly, read_back
from mesh_parts import tessellate_pair
from p21model import STR_RE, decode_p21
from p21split import Splitter
import provenance
from validate_parts import read_part


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def source_rotation(up):
    if up == 'z':
        return np.eye(4)
    if up in ('y', '-y'):
        sign = -1 if up.startswith('-') else 1
        return np.array([[1., 0, 0, 0], [0, 0, -sign, 0], [0, sign, 0, 0], [0, 0, 0, 1.]])
    raise ValueError(f'unsupported source up axis: {up}')


def branches(pkg, config):
    """Disjoint root occurrence branches, grouped only by exact product ID."""
    if len(pkg.m.roots) != 1:
        raise ValueError('expected one source assembly root')
    root = pkg.m.roots[0]
    groups = {}
    if pkg.bodies(root):
        groups[root] = {'name': 'arena', 'label': pkg.m.pname(root), 'occurrences': [], 'matrices': [np.eye(4)]}
    for edge, child in pkg.m.children.get(root, []):
        if child is None:
            raise ValueError('unresolved assembly child')
        pid = int(pkg.ix.ids[child])
        strings = STR_RE.findall(pkg.ix.args(edge))
        label = decode_p21(strings[2]) if len(strings) > 2 else pkg.m.pname(child)
        group = groups.setdefault(child, {'name': config.get('product_names', {}).get(str(pid), f'product-{pid}'),
                                         'label': label, 'occurrences': [], 'matrices': []})
        group['occurrences'].append(int(pkg.ix.ids[edge]))
        group['matrices'].append(pkg.nauo_T.get(edge, np.eye(4)))
    return groups


def export(pkg, config, out, policy, config_hash):
    out = Path(out)
    if out.exists():
        raise ValueError(f'output exists: {out}')
    if Path(pkg.source).name != config['source'] or sha256(pkg.source) != config['source_sha256']:
        raise ValueError('source filename or SHA-256 differs from configuration')
    unowned = [int(pkg.ix.ids[b]) for b, rep in pkg.m.bodies if rep not in pkg.m.rep_product]
    if unowned:
        raise ValueError(f'bodies without product ownership: {unowned}')
    groups = branches(pkg, config)
    # Compare occurrence-path counts, not only sets of unique bodies: a shared
    # product can legitimately appear both under a ramp and directly at root.
    expected = Counter(row for row, matrices in pkg.transforms.items() if pkg.bodies(row) for _ in matrices)
    actual = Counter()
    selections = {}
    for anchor, spec in groups.items():
        items = pkg.subtree_placed(anchor, np.eye(4))
        # A root with its own bodies must not swallow the child branches.
        if anchor == pkg.m.roots[0]:
            items = [(anchor, np.eye(4))]
        items = [(r, m) for r, m in items if pkg.bodies(r)]
        if not items:
            raise ValueError(f"empty source branch: {spec['name']}")
        selections[anchor] = items
        for row, _ in items:
            actual[row] += len(spec['matrices'])
    if actual != expected:
        raise ValueError('source occurrence coverage is incomplete or duplicated')
    out.mkdir(parents=True)
    (out / 'cad').mkdir()
    cache = out.parent / ('.' + config['id'] + '-mesh-cache')
    cache.mkdir(exist_ok=True)
    rotation = source_rotation(config['up_axis'])
    source_hash = config['source_sha256']
    assets, report, mesh_cache = {}, {}, {}
    split = Splitter(pkg.ix, pkg.m)
    full = {k: GlbWriter('FULL-MAP', provenance.glb_asset('export_source_package.py', pkg.source, source_hash,
                        frame='Z-up arena, metres', collision=k == 'collision')) for k in ('visual', 'collision')}
    t0 = time.time()
    for anchor, spec in groups.items():
        name = spec['name']
        print(f"exporting {name} ({spec['label']})", flush=True)
        items = selections[anchor]
        meshed = []
        counts = [0, 0]
        for row, matrix in items:
            part = pkg.part(row)
            settings = policy.settings(name, part['name'])
            key = (part['product_id'], json.dumps(settings, sort_keys=True))
            if key not in mesh_cache:
                fingerprint = hashlib.sha256((source_hash + repr(key)).encode()).hexdigest()[:20]
                saved = cache / (fingerprint + '.npz')
                if saved.exists():
                    with np.load(saved) as z:
                        pair = [tuple(z[f'{kind}{i}'] if i < 3 else json.loads(str(z[f'{kind}{i}']))
                                      for i in range(4)) for kind in ('v', 'c')]
                        stats = json.loads(str(z['stats']))
                        imported = z['counts'].tolist()
                else:
                    doc, reader, error = read_part(str(Path(pkg.pkg) / part['file']))
                    if error:
                        raise ValueError(f"{part['file']}: {error}")
                    imported = list(shape_counts(doc))
                    stats = {}
                    pair = tessellate_pair(doc, settings, stats=stats)
                    if any(mesh is None for mesh in pair) or stats.get('unmeshed_faces'):
                        raise ValueError(f"incomplete tessellation: {part['file']}: {stats}")
                    fields = {f'{kind}{i}': value if i < 3 else json.dumps(value)
                              for kind, mesh in zip(('v', 'c'), pair) for i, value in enumerate(mesh)}
                    np.savez(saved, **fields, counts=imported, stats=json.dumps(stats))
                    del doc, reader
                mesh_cache[key] = (pair, imported, stats)
                print(f"  product {part['product_id']} {part['name']}: {len(pair[0][1])}/{len(pair[1][1])} triangles", flush=True)
            pair, imported, stats = mesh_cache[key]
            counts = [a + b for a, b in zip(counts, imported)]
            meshed.append((row, matrix, pair, stats))
        # Local coordinates stay aligned to the source product. Recentring keeps
        # float32 vertices near the origin without changing source placements.
        clouds = [mesh[0][0] @ matrix[:3, :3].T + matrix[:3, 3] for _, matrix, mesh, _ in meshed]
        points = np.vstack(clouds) / 1000
        up = 2 if config['up_axis'] == 'z' else 1
        origin = (points.min(0) + points.max(0)) / 2
        origin[up] = points[:, up].max() if config['up_axis'].startswith('-') else points[:, up].min()
        writers = {k: GlbWriter(name, provenance.glb_asset('export_source_package.py', pkg.source, source_hash,
                               frame=f"source {config['up_axis']}-up local axes, metres", collision=k == 'collision'))
                   for k in ('visual', 'collision')}
        placements = []
        for i, matrix in enumerate(spec['matrices']):
            pl = rotation @ in_metres(matrix) @ translation(origin)
            placements.append(placement_entry(i, pl, 'source_occurrence', 0))
        for n, (row, matrix, meshes, stats) in enumerate(meshed):
            node = f'source_{int(pkg.ix.ids[row])}_{n}'
            local = in_metres(matrix)
            local[:3, 3] -= origin
            for kind, mesh in zip(('visual', 'collision'), meshes):
                p, tri, col, colours = mesh
                keys = [colours[int(c)] for c in col]
                writers[kind].add_node(node, p / 1000, tri, keys, matrix=local)
                for i, pl in enumerate(placements):
                    full[kind].add_node(f'{name}_{i}_{node}', p / 1000, tri, keys,
                                        matrix=np.asarray(pl['matrix_local_to_arena']) @ local)
        entry = {'label': spec['label'], 'source_product_id': int(pkg.ix.ids[anchor]),
                 'source_occurrence_ids': spec['occurrences'], 'source_products': sorted({int(pkg.ix.ids[r]) for r, _ in items}),
                 'placements_in_source_arena_frame': placements, 'in_full_map': True,
                 'bbox_local_m': [(points.min(0) - origin).tolist(), (points.max(0) - origin).tolist()],
                 'local_up_axis': config['up_axis'], 'motion_status': 'source rest pose; no reviewed 2027 joint binding',
                 'collision_method': 'independent source tessellation, solids and sheets retained'}
        for kind, writer in writers.items():
            filename = name + ('' if kind == 'visual' else '-collision') + '.glb'
            writer.write(str(out / filename))
            entry[kind] = filename
            entry[kind + '_sha256'] = sha256(out / filename)
            entry['triangles' if kind == 'visual' else 'collision_triangles'] = writer.triangles
        cad = out / 'cad' / (name + '.step')
        local_items = [(row, translation(-origin * 1000) @ matrix) for row, matrix in items]
        write_assembly(split, name, spec['label'], local_items, str(cad), source_hash, pkg)
        got, box, error = read_back(str(cad), 2, 0.35)
        residual = max(float(np.abs(box[0] - (points.min(0) - origin)).max()),
                       float(np.abs(box[1] - (points.max(0) - origin)).max())) if box is not None else None
        valid = not error and list(got) == counts and residual is not None and residual <= 0.005
        report[name] = {'ok': valid, 'source_imported_solids_faces': counts, 'assembly_imported_solids_faces': got,
                        'mesh_bbox_residual_m': residual, 'error': error,
                        'meshing': [{'product_id': int(pkg.ix.ids[r]), 'statistics': stats} for r, _, _, stats in meshed]}
        entry['step'] = {'file': 'cad/' + cad.name, 'sha256': sha256(cad), 'validation': report[name]}
        assets[name] = entry
        dump(out / 'validation.json', report)
        if not valid:
            raise ValueError(f'{name}: CAD read-back validation failed: {report[name]}')
        print(f"  validated {counts[1]} faces, {len(placements)} placements, bbox residual {residual:.6f} m", flush=True)
    for kind, writer in full.items():
        filename = 'full-map' + ('' if kind == 'visual' else '-collision') + '.glb'
        writer.write(str(out / filename))
        assets.setdefault('full-map', {'label': config['id'] + ' full map', 'in_full_map': False,
                                      'composed_of': list(report)})
        assets['full-map'][kind] = filename
        assets['full-map'][kind + '_sha256'] = sha256(out / filename)
        assets['full-map']['triangles' if kind == 'visual' else 'collision_triangles'] = writer.triangles
    manifest = {'schema_version': 1, 'generator': provenance.generator('export_source_package.py'),
                'units': 'metres', 'source_file': Path(pkg.source).name, 'source_sha256': source_hash,
                'arena_frame': 'right-handed Z-up arena; source_to_arena_matrix applied once in placements',
                'source_up_axis': config['up_axis'], 'source_to_arena_matrix': rotation.tolist(),
                'configuration_sha256': config_hash, 'export_policy': policy.metadata(),
                'source_configuration_sha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                'body_coverage': {'unique_bodies': len(pkg.m.bodies), 'placed_products': sum(expected.values()),
                                  'complete': actual == expected, 'unowned': unowned},
                'collision_contract': 'Source solids and sheets retained. No convex decomposition or inferred collision exclusions.',
                'motion_status': 'No 2026 joint bindings or reconstructed geometry transferred.', 'assets': assets}
    dump(out / 'manifest.json', manifest)
    semantic_rules = {'schema_version': 1, 'source_sha256': source_hash, 'assets': {}}
    for name, entry in assets.items():
        if name == 'full-map':
            continue
        semantic_rules['assets'][name] = {'id': name, 'input_sha256': {k: entry[k + '_sha256'] for k in ('visual', 'collision')},
            'nodes': [{'select': {'name': name}, 'metadata': {'id': name, 'roles': ['assembly']},
                       'evidence': ['Checksum-pinned source product and occurrence IDs; rest-pose geometry only.']}], 'joints': []}
    dump(out / 'semantic-rules.json', semantic_rules)
    annotate_package(out, semantic_rules, sha256(out / 'semantic-rules.json'))
    # The standard articulated exporter also handles fixed, single-link models.
    # This supplies SDF/URDF/USD equipment without inventing mechanical joints.
    from export_articulated import export as export_equipment
    export_equipment(out, out / 'simulators' / 'rm_map_equipment')
    manifest = json.loads((out / 'manifest.json').read_text())
    models = out / 'models'
    models.mkdir()
    catalog = {'schema_version': 1, 'copyright': provenance.COPYRIGHT, 'models': []}
    for name, entry in manifest['assets'].items():
        data = (out / entry['visual']).read_bytes()
        compressed = gzip.compress(data, compresslevel=9, mtime=0)
        (models / (name + '.glb.gz')).write_bytes(compressed)
        up_axis = 'z' if name == 'full-map' else config['up_axis']
        catalog['models'].append({'id': config['id'] + '-' + name, 'label': config['id'] + ' ' + entry['label'],
            'file': name + '.glb.gz', 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(compressed),
            'up': [0, 0, 1] if up_axis == 'z' else [0, -1 if up_axis == '-y' else 1, 0], 'joints': [],
            'note': 'Official 2027 CAD rest pose; mechanical joint bindings have not been established.'})
    dump(models / 'catalog.json', catalog)
    print(f"{config['id']}: {len(report)} assemblies validated in {time.time() - t0:.0f}s", flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('index')
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', type=Path, required=True)
    add_arguments(parser)
    args = parser.parse_args()
    policy = from_arguments(args, parser)
    config = json.loads(args.config.read_text())
    if config.get('schema_version') != 1:
        parser.error('unsupported source configuration')
    selected = next(c for c in config['sources'] if c['id'] == args.source)
    export(Package(args.package, args.index), selected, args.out, policy, sha256(args.config))


if __name__ == '__main__':
    main()
