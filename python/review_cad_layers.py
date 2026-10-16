#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Review layer qualification against exact topology and a pinned motion profile.

Analysis only: no geometry, styles, collision policies or runtime bindings change.
Source layers remain source layers. A reviewed simulation-motion profile is
independent evidence, not a claim that the STEP defines motion or mechanical stops.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from audit_semantic_evidence import semantic_evidence
from cad_document import CadDocument
from p21model import BODY_TYPES


def validate_profile(document, profile):
    """Resolve explicit product/body motion assignments, rejecting stale or overlapping rules."""
    if profile.get('schema_version') != 1 or profile.get('source_sha256') != document.source_sha256:
        raise ValueError('motion profile schema/source SHA-256 mismatch')
    ix, model = document.index, document.model
    owners = defaultdict(set)
    for body, rep in model.bodies:
        product = model.rep_product.get(rep)
        if product is not None:
            owners[int(ix.ids[body])].add(int(ix.ids[product]))
    result = {}
    for entry in profile['assignments']:
        if entry['motion'] not in ('fixed', 'moving') or not entry.get('evidence') or not entry.get('motion_owner'):
            raise ValueError('motion assignment needs fixed/moving, motion_owner and evidence')
        product = entry['product_id']
        if product not in {int(ix.ids[p]) for p in model.product_name}:
            raise ValueError('unknown product')
        for body in entry['body_ids']:
            key = (product, body)
            if key in result or product not in owners[body]:
                raise ValueError('duplicate assignment or body not owned by selected product')
            result[key] = (entry['motion'], entry['motion_owner'])
    return result


def review_layers(document, profile):
    """Qualify grouping granularity and reject masks crossing known motion/colour boundaries.

    RGB diagnostics use the existing typed model's rounded four-decimal effective
    surface colour, including body/shell fallback. They are not an appearance
    equivalence proof; original style records remain authoritative.
    """
    motion = validate_profile(document, profile)
    ix, model = document.index, document.model
    audit = semantic_evidence(ix, model)
    bodies = {}
    face_rgb = {}
    owners = defaultdict(set)
    for body, rep in model.bodies:
        product = model.rep_product.get(rep)
        if product is not None:
            owners[int(ix.ids[body])].add(int(ix.ids[product]))
    for body in ix.rows_of(*BODY_TYPES):
        body = int(body)
        faces = model.body_faces_shells(body)
        bodies[int(ix.ids[body])] = {int(ix.ids[f]) for f, _ in faces}
        bc = model.surface_colour(body)
        for face, shell in faces:
            # Keep every possible owner colour for a shared source face.
            face_rgb.setdefault(int(ix.ids[face]), set()).add(
                model.surface_colour(face) or model.surface_colour(shell) or bc or 'unresolved')
    product_labels = defaultdict(set)
    for occurrence in audit['assembly_occurrences']:
        product_labels[occurrence['child_product_id']].add(occurrence['strings'][-1])
    groups = []
    for group in audit['layer_memberships']:
        layer = ix.r(group['layers'][0]['source_id'])
        refs = ix.refs_of(layer)
        direct_faces = set()
        whole_bodies = set()
        for ref in refs:
            row = ix.r(int(ref))
            if row >= 0 and ix.tname(row) == 'ADVANCED_FACE':
                direct_faces.add(int(ref))
            if row >= 0 and ix.tname(row) in BODY_TYPES:
                whole_bodies.add(int(ref))
        represented_faces = direct_faces | set().union(*(bodies[b] for b in whole_bodies))
        touched = group['referenced_body_ids']
        coverage = [{'body_id': b, 'faces_in_layer': len(bodies[b] & represented_faces),
                     'source_faces': len(bodies[b]), 'whole_body_reference': b in whole_bodies}
                    for b in touched]
        if not touched:
            scope = 'no_resolved_body'
        elif len(touched) > 1:
            scope = 'multi_body_group'
        elif bodies[touched[0]] and bodies[touched[0]] <= represented_faces:
            scope = 'complete_single_body'
        else:
            scope = 'partial_single_body'
        roles = Counter()
        rigid_owners = Counter()
        for body in touched:
            assigned = {motion.get((p, body), ('unknown', 'unknown')) for p in owners[body]}
            role, owner = next(iter(assigned)) if len(assigned) == 1 else ('unknown', 'unknown')
            roles[role] += 1
            rigid_owners[owner] += 1
        palette = Counter()
        for face in represented_faces:
            palette.update(face_rgb.get(face, {'unresolved'}))
        known_palette = set(palette)-{'unresolved'}
        crossed = bool(roles['fixed'] and roles['moving'])
        hints = {h for layer in group['layers'] for h in layer['name_hints']}
        findings = []
        if 'lighting' in hints and len(touched) > 1:
            findings.append('Reject as an individual light mask: selects multiple bodies.')
        if 'colour' in hints and len(known_palette) > 1:
            findings.append('Reject as a single-colour mask: multiple effective RGB values are present.')
        if crossed:
            findings.append('Reject as one rigid batch: crosses reviewed moving/fixed body boundary.')
        if len(set(rigid_owners)-{'unknown'}) > 1:
            findings.append('Preserve independently controlled rigid owners; movement alone is not one batch owner.')
        if scope == 'complete_single_body':
            findings.append('Candidate component selector; physical function and appearance control still need review.')
        groups.append({
            'membership_sha256': group['membership_sha256'], 'layers': group['layers'],
            'scope': scope, 'body_coverage': coverage,
            'owner_products': [{'product_id': p, 'occurrence_labels': sorted(product_labels[p])}
                               for p in group['referenced_owner_product_ids']],
            'reviewed_motion_body_counts': dict(roles),
            'reviewed_motion_owner_body_counts': dict(rigid_owners), 'crosses_reviewed_motion_boundary': crossed,
            'effective_face_rgb_4dp_counts': dict(sorted(palette.items())),
            'review_findings': findings, 'physical_role': 'unknown',
            'collision_exclusion_qualified': False, 'light_mask_qualified': False,
        })
    document.verify_source()
    return {
        'schema_version': 1, 'mode': 'analysis-only', 'source_sha256': document.source_sha256,
        'source_unchanged': True, 'profile': profile,
        'summary': {'membership_groups': len(groups),
                    'scope_counts': dict(Counter(g['scope'] for g in groups)),
                    'reviewed_motion_assignments': dict(Counter(role for role, owner in motion.values())),
                    'groups_crossing_reviewed_motion_boundary': sum(g['crosses_reviewed_motion_boundary'] for g in groups),
                    'qualified_light_masks': 0, 'qualified_collision_exclusions': 0},
        'groups': groups,
        'limitations': [
            'Reviewed motion applies to all occurrences of the specified product in the existing simulation adapter.',
            'Profiles describe current simulated motion, not complete mechanical capability or rulebook requirements.',
            'Source style targets and curves are not recursively promoted to geometric layer membership.',
            'RGB values are rounded diagnostics, not exact material equivalence or decoration evidence.',
            'Complete single-body membership qualifies only as a component selector, never a gameplay role.',
            'No binding, batching, artwork conversion or collision exclusion is applied.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='STEP or optional parser cache')
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('report exists; choose a new path')
    profile = json.loads(args.profile.read_text())
    loader = CadDocument.from_index if args.source.suffix == '.npz' else CadDocument.from_step
    with loader(args.source, expected_sha256=profile['source_sha256']) as doc:
        report = review_layers(doc, profile)
    report['profile_sha256'] = hashlib.sha256(args.profile.read_bytes()).hexdigest()
    report['producer_sha256'] = {p: hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest()
                                for p in ('review_cad_layers.py', 'audit_semantic_evidence.py',
                                          'cad_document.py', 'p21index.py', 'p21model.py')}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
