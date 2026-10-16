#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Discover whole-body work groups using source-qualified product-local regions.

Bounds come from original topological vertex points, not curved surface extrema.
These queries suggest groups; they never crop geometry, certify containment of
curved surfaces, merge bodies or assign mechanical/lighting/collision roles.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
from cad_document import CadDocument
from review_cad_layers import validate_profile


def classify_box(low, high, region_low, region_high):
    """Classify complete vertex boxes; a center inside a region is insufficient."""
    if np.all(low >= region_low) and np.all(high <= region_high):
        return 'contained'
    if np.all(high >= region_low) and np.all(low <= region_high):
        return 'straddling'
    return 'outside'


def audit_regions(document, plan, motion_profile):
    """Report contained, straddling, unbounded and explicitly motion-excluded bodies."""
    if plan.get('schema_version') != 1 or plan.get('source_sha256') != document.source_sha256:
        raise ValueError('region plan schema/source SHA-256 mismatch')
    units = document.geometry_length_units
    if plan.get('coordinate_frame') != 'product-local' or plan.get('length_unit') != 'millimetre':
        raise ValueError('regions require explicit product-local millimetres')
    if not units or set(units) != {'.MILLI.,.METRE.'}:
        raise ValueError('source geometry length units are not exclusively millimetres')
    motion = validate_profile(document, motion_profile)
    ix, model = document.index, document.model
    owned = defaultdict(set)
    for body, representation in model.bodies:
        product = model.rep_product.get(representation)
        if product is not None:
            owned[int(ix.ids[product])].add(int(ix.ids[body]))
    shell_records = []
    for body in plan.get('surface_model_body_ids', []):
        row = ix.r(body)
        if row < 0 or ix.tname(row) != 'SHELL_BASED_SURFACE_MODEL':
            raise ValueError('shell inspection requires an original surface-model body')
        products = [p for p, ids in owned.items() if body in ids]
        for source_shell in ix.refs_of(row):
            shell_row = ix.r(int(source_shell))
            if shell_row < 0 or ix.tname(shell_row) not in ('OPEN_SHELL', 'CLOSED_SHELL'):
                raise ValueError('surface model contains unsupported shell references')
            a, b, vertices = model.body_bbox(shell_row)
            shell_records.append({'source_body_id': body, 'shell_id': int(source_shell),
                                  'owner_product_ids': products,
                                  'source_faces': len(model.body_faces(shell_row)),
                                  'min_mm': a.tolist() if a is not None else None,
                                  'max_mm': b.tolist() if b is not None else None})
    bounds, results, names = {}, [], set()
    for region in plan['regions']:
        identity, product = region['id'], region['product_id']
        if identity in names or product not in owned or not region.get('evidence'):
            raise ValueError('region needs unique identity, known product and evidence')
        names.add(identity)
        low, high = [np.asarray(region[k], dtype=float) for k in ('min_mm', 'max_mm')]
        if (low.shape != (3,) or high.shape != (3,) or not np.isfinite([low, high]).all()
                or np.any(high <= low)):
            raise ValueError('region bounds must be finite ordered three-dimensional vectors')
        expected = region['expected_body_ids']
        if len(set(expected)) != len(expected) or not set(expected) <= owned[product]:
            raise ValueError('expected body IDs must be distinct and owned by the region product')
        motion_filter = region.get('motion_filter')
        if motion_filter is not None and (motion_filter.get('motion') not in ('fixed', 'moving')
                                          or not motion_filter.get('motion_owner')):
            raise ValueError('motion filter needs explicit reviewed motion and owner')
        matches = defaultdict(list)
        for body in sorted(owned[product]):
            if body not in bounds:
                a, b, vertices = model.body_bbox(ix.r(body))
                bounds[body] = {'body_id': body, 'min_mm': a.tolist() if a is not None else None,
                                'max_mm': b.tolist() if b is not None else None,
                                'topological_vertices': vertices}
            box = bounds[body]
            if box['min_mm'] is None:
                matches['unbounded_body_ids'].append(body)
                continue
            relation = classify_box(np.asarray(box['min_mm']), np.asarray(box['max_mm']), low, high)
            if relation == 'outside':
                continue
            if motion_filter and motion.get((product, body)) != (motion_filter['motion'], motion_filter['motion_owner']):
                matches['excluded_by_motion_body_ids'].append(body)
                continue
            matches[relation+'_body_ids'].append(body)
        actual = set(matches['contained_body_ids'])
        shell_matches = defaultdict(list)
        for shell in shell_records:
            if product not in shell['owner_product_ids']:
                continue
            if shell['min_mm'] is None:
                shell_matches['unbounded_shell_ids'].append(shell['shell_id'])
                continue
            relation = classify_box(np.asarray(shell['min_mm']), np.asarray(shell['max_mm']), low, high)
            if relation != 'outside':
                shell_matches[relation+'_shell_ids'].append(shell['shell_id'])
        results.append({'id': identity, 'product_id': product,
                        'min_mm': low.tolist(), 'max_mm': high.tolist(), 'motion_filter': motion_filter,
                        'evidence': region['evidence'],
                        **{k: matches[k] for k in ('contained_body_ids', 'straddling_body_ids',
                                                  'excluded_by_motion_body_ids', 'unbounded_body_ids')},
                        'shell_candidates': {k: shell_matches[k] for k in ('contained_shell_ids',
                                                                         'straddling_shell_ids', 'unbounded_shell_ids')},
                        'shell_motion_filter_applied': False,
                        'expected_body_ids': expected,
                        'unexpected_body_ids': sorted(actual-set(expected)),
                        'missing_body_ids': sorted(set(expected)-actual),
                        'expected_membership_matches': actual == set(expected),
                        'qualification': 'spatial-candidate', 'functional_role': 'unknown'})
    document.verify_source()
    return {'schema_version': 1, 'mode': 'analysis-only', 'source_sha256': document.source_sha256,
            'source_unchanged': True, 'summary': {'regions': len(results),
                'matching_expected_memberships': sum(r['expected_membership_matches'] for r in results),
                'regions_with_straddling_bodies': sum(bool(r['straddling_body_ids']) for r in results)},
            'regions': results, 'body_vertex_bounds': list(bounds.values()),
            'source_shells': shell_records,
            'shells_in_multiple_regions': [{'shell_id': sid, 'regions': regions} for sid, regions in
                _shell_owners(results).items() if len(regions) > 1],
            'limitations': ['Topological vertex bounds can miss extrema of curved edges/surfaces.',
                'Straddling bodies are reported, never clipped or silently assigned by their centers.',
                'Exact expected membership is a reproducibility check, not functional or geometric certification.',
                'Explicit reviewed motion filters are separate evidence; unknown motion is not fixed.',
                'Shell candidates preserve existing shell boundaries; they are not assigned to components or exported.',
                'Shell candidates ignore body motion filters: parent motion may need review for their real function.',
                'Overlapping shell candidates are reported and never assigned to multiple components automatically.',
                'All proposed groups require visual/functional review.']}


def _shell_owners(regions):
    owners = defaultdict(list)
    for region in regions:
        for shell in region['shell_candidates']['contained_shell_ids']:
            owners[shell].append(region['id'])
    return owners


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--motion-profile', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    profile = json.loads(args.motion_profile.read_text())
    loader = CadDocument.from_index if args.source.suffix == '.npz' else CadDocument.from_step
    with loader(args.source, expected_sha256=plan['source_sha256']) as document:
        result = audit_regions(document, plan, profile)
    result['producer_sha256'] = {p: hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest()
                                for p in ('audit_component_regions.py', 'cad_document.py', 'p21model.py',
                                          'p21index.py', 'review_cad_layers.py', 'audit_step.py')}
    result['plan_sha256'] = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    result['motion_profile_sha256'] = hashlib.sha256(args.motion_profile.read_bytes()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
