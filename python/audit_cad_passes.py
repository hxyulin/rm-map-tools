#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Run non-mutating CAD optimization discovery passes on an in-memory STEP document.

No healing, tessellation, shape approximation, deletion or export is performed.
Exact graph matches are geometry-sharing evidence, not permission to merge
styles, source identities, occurrences or independently moving equipment.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from audit_geometry_duplicates import GeometryFingerprints
from cad_document import CadDocument
from audit_semantic_evidence import semantic_evidence
from p21model import BODY_TYPES


def file_hash(path):
    """Stream SHA-256 without retaining another copy of a large source file."""
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def assembly_reuse(ix, model, transforms):
    """Inventory existing product occurrences with their complete assembly paths.

    Missing, non-rigid or reflected placements are reported and not replaced by
    identity transforms. Cycles stop the audit. Translations retain source units.
    Counts include subassemblies and must not be added to descendant body counts.
    """
    placed = defaultdict(list)
    issues = []

    def walk(product, matrix, path, ancestors):
        if product in ancestors:
            raise ValueError('cyclic assembly graph')
        placed[product].append({'occurrence_path': [int(ix.ids[r]) for r in path],
                                'source_world_matrix': matrix.tolist()})
        for occurrence, child in model.children.get(product, []):
            local = transforms.get(occurrence)
            if (child is None or local is None or not rigid(local)):
                issues.append({'occurrence_id': int(ix.ids[occurrence]),
                               'reason': 'missing child/explicit transform or non-rigid/reflected transform'})
                continue
            walk(child, matrix @ local, path+[occurrence], ancestors | {product})

    for root in model.roots:
        walk(root, np.eye(4), [], set())
    groups = [{'product_id': int(ix.ids[p]), 'name': model.pname(p),
               'occurrences': occurrences} for p, occurrences in placed.items() if len(occurrences) > 1]
    groups.sort(key=lambda g: (-len(g['occurrences']), g['product_id']))
    return {'product_definitions_visited': len(placed),
            'placed_product_occurrences': sum(map(len, placed.values())),
            'repeated_products': len(groups),
            'additional_product_occurrences': sum(len(g['occurrences'])-1 for g in groups),
            'groups': groups, 'issues': issues,
            'unvisited_product_ids': sorted(int(ix.ids[p]) for p in model.product_reps if p not in placed),
            'interpretation': 'Existing CAD reuse, potentially already instanced by exporters; not new triangle savings.'}


def rigid(matrix):
    """Accept finite affine, orientation-preserving rigid placements, without fitting."""
    m = np.asarray(matrix)
    return (m.shape == (4, 4) and np.isfinite(m).all()
            and np.allclose(m[3], [0, 0, 0, 1], atol=1e-12, rtol=0)
            and np.allclose(m[:3, :3].T @ m[:3, :3], np.eye(3), atol=1e-9, rtol=0)
            and abs(np.linalg.det(m[:3, :3])-1) < 1e-9)


def exact_body_reuse(ix, model):
    """Match unchanged, ordered STEP geometry graphs, ignoring IDs and display names.

    Numeric spellings, coordinates, surface parameters, topology order and
    orientation remain significant. This deliberately misses equivalent shapes
    encoded differently. Styles and semantic bindings are outside these hashes.
    """
    fingerprints = GeometryFingerprints(ix)
    owners = defaultdict(set)
    for body, representation in model.bodies:
        product = model.rep_product.get(representation)
        if product is not None:
            owners[body].add(int(ix.ids[product]))
    groups = defaultdict(list)
    skipped = []
    bodies = ix.rows_of(*BODY_TYPES)
    for body in bodies:
        body = int(body)
        try:
            key = fingerprints.signature(body).hex()
            groups[key].append(body)
        except (ValueError, RecursionError) as error:
            skipped.append({'body_id': int(ix.ids[body]), 'reason': str(error)})
    matches = []
    for signature, rows in groups.items():
        if len(rows) < 2:
            continue
        matches.append({'geometry_sha256': signature, 'type': ix.tname(rows[0]),
                        'representative_body_id': int(ix.ids[rows[0]]),
                        'bodies': [{'body_id': int(ix.ids[r]), 'owner_product_ids': sorted(owners[r])}
                                   for r in rows],
                        'appearance_equivalence': 'not checked; preserve per-occurrence/face styles',
                        'semantic_equivalence': 'not checked; preserve every original source binding'})
    matches.sort(key=lambda g: (-len(g['bodies']), g['representative_body_id']))
    return {'body_definitions': len(bodies), 'hashed_body_definitions': sum(map(len, groups.values())),
            'unique_geometry_fingerprints': len(groups), 'duplicate_groups': len(matches),
            'redundant_body_definitions': sum(len(g['bodies'])-1 for g in matches),
            'groups': matches, 'skipped': skipped,
            'interpretation': 'Potential shared geometry definitions; retain all placed occurrences and contacts. No triangle reduction is claimed.'}


# A pass describes its effect before it can enter the runner. Mutating passes
# belong in a separate, future apply pipeline with an explicit reviewed plan.
PASSES = {
    'semantic-evidence': {'version': 1, 'effect': 'read-only',
                          'description': 'Layer, assembly, appearance and motion evidence; unresolved roles stay unknown'},
    'assembly-reuse': {'version': 1, 'effect': 'read-only',
                       'description': 'Existing product occurrences and explicit rigid placements'},
    'exact-body-reuse': {'version': 1, 'effect': 'read-only',
                         'description': 'Byte-conservative STEP geometry graph duplicates'},
}


def validate_passes(names):
    if not names or len(names) != len(set(names)) or any(n not in PASSES for n in names):
        raise ValueError('choose distinct registered passes')
    if any(PASSES[n]['effect'] != 'read-only' for n in names):
        raise ValueError('this runner admits read-only passes only')


def run_document(document, names):
    """Run discovery on an already loaded document, without reindexing or importing CAD."""
    validate_passes(names)
    started = time.perf_counter()
    ix, model = document.index, document.model
    if len(ix.mm) != ix.size:
        raise ValueError('source size differs from index')
    results = []
    for name in names:
        print(f'CAD audit: {name}', flush=True)
        if name == 'semantic-evidence':
            findings = semantic_evidence(ix, model)
        elif name == 'assembly-reuse':
            findings = assembly_reuse(ix, model, document.transforms)
        elif name == 'exact-body-reuse':
            findings = exact_body_reuse(ix, model)
        else:
            raise ValueError('registered pass has no implementation')
        results.append({'id': name, **PASSES[name], 'findings': findings})
    document.verify_source()
    return {'schema_version': 1, 'mode': 'analysis-only', 'actions': [],
            'inputs': {'source': str(document.source_path), 'source_sha256': document.source_sha256,
                       'source_bytes': ix.size},
            'producer_sha256': {p: file_hash(Path(__file__).with_name(p)) for p in
                ('audit_cad_passes.py', 'audit_semantic_evidence.py', 'cad_document.py', 'audit_geometry_duplicates.py',
                 'p21index.py', 'p21model.py', 'mesh_parts.py')},
            'source_unchanged': True, 'passes': results,
            'elapsed_seconds': time.perf_counter()-started,
            'limitations': ['No CAD model, mesh or installed package is written.',
                'Shared definitions can reduce storage, tessellation work and mesh uploads; placed triangles/contacts remain.',
                'A future apply stage must preserve face styles, source identities, placements, motion, scoring and collision ownership.',
                'Exact graph matching is sufficient but incomplete: no quantization, coordinate normalization, reflection or geometric fitting.']}


def run(index, source_sha256, names, *, workers=None):
    """Read STEP directly or use an optional index cache, through the same document API."""
    validate_passes(names)
    path = Path(index)
    direct = path.suffix.lower() in {'.stp', '.step'}
    index_digest = None if direct else file_hash(path)
    loader = CadDocument.from_step if direct else CadDocument.from_index
    options = {'expected_sha256': source_sha256}
    if direct:
        options['workers'] = workers
    started = time.perf_counter()
    with loader(path, **options) as document:
        loaded = time.perf_counter()
        report = run_document(document, names)
        report['load_seconds'] = loaded-started
        report['total_seconds'] = time.perf_counter()-started
        if not direct and file_hash(path) != index_digest:
            raise ValueError('input index changed during audit; discard results')
        report['inputs'].update(index=None if direct else str(path.resolve()), index_sha256=index_digest)
        report['source_and_index_unchanged'] = True
        return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('index', type=Path, nargs='?', help='original STEP or optional .npz parser cache')
    ap.add_argument('--workers', type=int, default=4, help='STEP indexing worker count')
    ap.add_argument('--source-sha256')
    ap.add_argument('--out', type=Path, help='new JSON report; existing paths are refused')
    ap.add_argument('--passes', nargs='+', choices=list(PASSES), default=list(PASSES))
    ap.add_argument('--list-passes', action='store_true')
    args = ap.parse_args()
    if args.list_passes:
        print(json.dumps(PASSES, indent=2))
        return
    if not args.index or not args.out or not args.source_sha256:
        ap.error('index, --source-sha256 and --out are required')
    if args.out.exists():
        ap.error('report already exists; choose a new path')
    report = run(args.index, args.source_sha256, args.passes, workers=args.workers)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting anything if another run wins.
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'report': str(args.out), 'source_unchanged': True,
                      'passes': [{k: v for k, v in p['findings'].items() if k not in ('groups', 'skipped', 'layer_memberships', 'products', 'assembly_occurrences', 'source_type_counts')}
                                 for p in report['passes']]}, indent=2))


if __name__ == '__main__':
    main()
