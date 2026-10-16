#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Lossless representation passes over a derived, source-owned in-memory CAD scene.

Share exact geometry or presentation definitions while retaining all source
identities, face styles, assembly instances and physical contact occurrences.
Source STEP and native XCAF are never modified. No tessellation is performed.
"""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
from itertools import zip_longest

import numpy as np
from pathlib import Path
from types import MappingProxyType

from audit_geometry_duplicates import GeometryFingerprints
from cad_document import CadDocument
from p21model import BODY_TYPES


@dataclass(frozen=True)
class BodyOccurrence:
    """One original body occurrence; only its shared geometry reference may change."""
    root_product_id: int
    product_id: int
    occurrence_path: tuple
    source_body_id: int
    geometry_body_id: int
    matrix: object  # Source-unit, product-to-source matrix; no fitting or rounding.


@dataclass(frozen=True)
class CadScene:
    """Derived references over immutable source data, separate from native CAD mutation.

    Appearance stays attached to source entities. Sharing geometry never shares
    source style bindings or source/robot identities. Keep the document open.
    """
    document: CadDocument
    revision: int = 0
    geometry_aliases: object = field(default_factory=dict)
    appearance_aliases: object = field(default_factory=dict)
    face_aliases: object = field(default_factory=dict)

    def __post_init__(self):
        for name in ('geometry_aliases', 'appearance_aliases', 'face_aliases'):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @staticmethod
    def _resolve(aliases, entity_id):
        seen = set()
        while entity_id in aliases:
            if entity_id in seen:
                raise ValueError('cyclic derived aliases')
            seen.add(entity_id)
            entity_id = aliases[entity_id]
        return entity_id

    def geometry(self, body_id):
        self.document.require_open()
        return self._resolve(self.geometry_aliases, body_id)

    def appearance(self, assignment_id):
        self.document.require_open()
        return self._resolve(self.appearance_aliases, assignment_id)

    def geometry_face(self, source_body_id, source_face_id):
        """Resolve a face within its body's sharing context, retaining the style owner.

        A source face can belong to several bodies. Its remapping must not leak
        into another body that retains a different canonical definition.
        """
        self.document.require_open()
        seen = set()
        while source_body_id in self.geometry_aliases:
            if source_body_id in seen:
                raise ValueError('cyclic derived aliases')
            seen.add(source_body_id)
            source_face_id = self.face_aliases.get((source_body_id, source_face_id), source_face_id)
            source_body_id = self.geometry_aliases[source_body_id]
        return source_face_id

    def occurrences(self):
        """Yield every placed source body, including coincident and repeated instances."""
        doc, owners = self.document, {}
        for body, rep in doc.model.bodies:
            product = doc.model.rep_product.get(rep)
            owners.setdefault(product, []).append(int(doc.index.ids[body]))
        for root in doc.model.roots:
            for product, matrix, path in doc.subtree(root):
                for body_id in owners.get(product, []):
                    frozen = matrix.copy()
                    frozen.flags.writeable = False
                    yield BodyOccurrence(int(doc.index.ids[root]), int(doc.index.ids[product]),
                        tuple(int(doc.index.ids[r]) for r in path), body_id, self.geometry(body_id), frozen)

    def style_bindings(self):
        """Yield original style ID/target and resolved assignment references, in order.

        The original record remains authoritative for override/context semantics.
        Presentation sharing never deletes bindings or merges their targets.
        """
        doc = self.document
        for ref in doc.entities('STYLED_ITEM', 'OVER_RIDING_STYLED_ITEM'):
            refs = ref.reference_ids
            over = ref.kind == 'OVER_RIDING_STYLED_ITEM'
            target = int(refs[-2] if over else refs[-1])
            assignments = refs[:-2] if over else refs[:-1]
            yield ref.id, target, tuple(self.appearance(int(r)) for r in assignments)

    def statistics(self):
        ix = self.document.index
        bodies = [int(ix.ids[r]) for r in ix.rows_of(*BODY_TYPES)]
        appearance = [int(ix.ids[r]) for r in ix.rows_of('PRESENTATION_STYLE_ASSIGNMENT')]
        return {'source_body_definitions': len(bodies),
                'shared_geometry_definitions': len({self.geometry(r) for r in bodies}),
                'source_appearance_definitions': len(appearance),
                'shared_appearance_definitions': len({self.appearance(r) for r in appearance}),
                'source_style_bindings': len(ix.rows_of('STYLED_ITEM', 'OVER_RIDING_STYLED_ITEM')),
                'mapped_source_faces': len(self.face_aliases)}


@dataclass(frozen=True)
class Redirect:
    """Exact source graph evidence and optional bijective source-face correspondence."""
    source_id: int
    canonical_id: int
    graph_sha256: str
    face_pairs: tuple = ()


@dataclass(frozen=True)
class PassPlan:
    """Inspectable, source- and revision-bound change proposal; no mutable payloads."""
    pass_id: str
    source_sha256: str
    revision: int
    redirects: tuple
    skipped: tuple


PASSES = {
    'share-exact-geometry': {'version': 1, 'effect': 'derived-scene-only',
                            'description': 'Intern identical B-rep graphs with bijective face correspondence'},
    'share-exact-appearance': {'version': 1, 'effect': 'derived-scene-only',
                              'description': 'Intern identical presentation graphs, retaining all strings and bindings'},
}


def face_correspondence(document, source, canonical):
    """Require a bijection of original STEP faces; graph similarity alone is insufficient."""
    ix = document.index
    stack, seen, forward, reverse = [(source, canonical)], set(), {}, {}
    while stack:
        a, b = stack.pop()
        if (a, b) in seen:
            continue
        seen.add((a, b))
        if ix.tname(a) != ix.tname(b):
            raise ValueError('geometry entity types differ')
        if ix.tname(a) == 'ADVANCED_FACE':
            if (a in forward and forward[a] != b) or (b in reverse and reverse[b] != a):
                raise ValueError('source face correspondence is not bijective')
            forward[a], reverse[b] = b, a
        ar, br = ix.refs_of(a), ix.refs_of(b)
        if len(ar) != len(br):
            raise ValueError('geometry reference counts differ')
        for x, y in zip(ar, br):
            xr, yr = ix.r(int(x)), ix.r(int(y))
            if xr < 0 or yr < 0:
                raise ValueError('unresolved geometry reference')
            stack.append((xr, yr))
    expected_a = set(document.model.body_faces(source))
    expected_b = set(document.model.body_faces(canonical))
    if set(forward) != expected_a or set(reverse) != expected_b:
        raise ValueError('incomplete source face correspondence')
    return tuple(sorted((int(ix.ids[a]), int(ix.ids[b])) for a, b in forward.items() if a != b))


def plan_pass(scene, pass_id):
    """Discover exact sharing on canonical definitions, without modifying scene or source."""
    if pass_id not in PASSES:
        raise ValueError('unknown CAD pass')
    doc, geometry = scene.document, pass_id == 'share-exact-geometry'
    doc.require_open()
    ix = doc.index
    hashes = GeometryFingerprints(ix, ignore_display_names=geometry)
    kinds = BODY_TYPES if geometry else ('PRESENTATION_STYLE_ASSIGNMENT',)
    resolve = scene.geometry if geometry else scene.appearance
    groups, redirects, skipped = {}, [], []
    for row in ix.rows_of(*kinds):
        row, entity_id = int(row), int(ix.ids[row])
        if resolve(entity_id) != entity_id:
            continue
        try:
            signature = hashes.signature(row).hex()
            canonical = groups.setdefault(signature, row)
            if canonical == row:
                continue
            faces = face_correspondence(doc, row, canonical) if geometry else ()
            redirects.append(Redirect(entity_id, int(ix.ids[canonical]), signature, faces))
        except (ValueError, RecursionError) as error:
            skipped.append((entity_id, str(error)))
    return PassPlan(pass_id, doc.source_sha256, scene.revision, tuple(redirects), tuple(skipped))


def apply_plan(scene, plan):
    """Validate every redirect, then return a new scene atomically; the input remains intact."""
    if (plan.pass_id not in PASSES or plan.source_sha256 != scene.document.source_sha256
            or plan.revision != scene.revision):
        raise ValueError('plan belongs to another source or scene revision')
    doc = scene.document
    doc.verify_source()
    geometry = plan.pass_id == 'share-exact-geometry'
    hashes = GeometryFingerprints(doc.index, ignore_display_names=geometry)
    allowed = set(doc.index.rows_of(*(BODY_TYPES if geometry else ('PRESENTATION_STYLE_ASSIGNMENT',))).tolist())
    aliases = dict(scene.geometry_aliases if geometry else scene.appearance_aliases)
    faces = dict(scene.face_aliases)
    seen = set()
    for redirect in plan.redirects:
        a, b = doc.index.r(redirect.source_id), doc.index.r(redirect.canonical_id)
        if (a not in allowed or b not in allowed or a == b or redirect.source_id in seen
                or redirect.source_id in aliases or redirect.canonical_id in aliases):
            raise ValueError('invalid or noncanonical redirect')
        seen.add(redirect.source_id)
        if hashes.signature(a).hex() != redirect.graph_sha256 or hashes.signature(b).hex() != redirect.graph_sha256:
            raise ValueError('redirect graph evidence does not match source')
        if geometry and face_correspondence(doc, a, b) != redirect.face_pairs:
            raise ValueError('redirect face evidence does not match source')
        if not geometry and redirect.face_pairs:
            raise ValueError('appearance redirect carries geometry evidence')
        aliases[redirect.source_id] = redirect.canonical_id
        for source_face, canonical_face in redirect.face_pairs:
            key = (redirect.source_id, source_face)
            if key in faces and faces[key] != canonical_face:
                raise ValueError('conflicting source-face mappings')
            faces[key] = canonical_face
    doc.verify_source()
    if not plan.redirects:
        return scene
    return CadScene(doc, scene.revision+1,
        aliases if geometry else scene.geometry_aliases,
        scene.appearance_aliases if geometry else aliases, faces)


def validate_equivalence(before, after):
    """Check all placed body identities/matrices and style targets/graphs after passes.

    This checks the derived reference scene, not a tessellated or kernel-exported
    model. Every changed reference must still name the exact original graph.
    """
    if before.document is not after.document:
        raise ValueError('scenes use different source documents')
    doc = before.document
    geometry = GeometryFingerprints(doc.index)
    appearance = GeometryFingerprints(doc.index, ignore_display_names=False)
    marker, occurrences, styles = object(), 0, 0
    for a, b in zip_longest(before.occurrences(), after.occurrences(), fillvalue=marker):
        if a is marker or b is marker:
            raise ValueError('body occurrence count changed')
        if ((a.root_product_id, a.product_id, a.occurrence_path, a.source_body_id)
                != (b.root_product_id, b.product_id, b.occurrence_path, b.source_body_id)
                or not np.array_equal(a.matrix, b.matrix)):
            raise ValueError('source identity or placement changed')
        if a.geometry_body_id != b.geometry_body_id:
            ar, br = doc.index.r(a.geometry_body_id), doc.index.r(b.geometry_body_id)
            if geometry.signature(ar) != geometry.signature(br):
                raise ValueError('placed geometry changed')
        occurrences += 1
    for a, b in zip_longest(before.style_bindings(), after.style_bindings(), fillvalue=marker):
        if a is marker or b is marker or a[:2] != b[:2] or len(a[2]) != len(b[2]):
            raise ValueError('source style binding changed')
        for old, new in zip(a[2], b[2]):
            if old != new and appearance.signature(doc.index.r(old)) != appearance.signature(doc.index.r(new)):
                raise ValueError('source style graph changed')
        styles += 1
    for (_, source_face), canonical_face in after.face_aliases.items():
        if geometry.signature(doc.index.r(source_face)) != geometry.signature(doc.index.r(canonical_face)):
            raise ValueError('mapped source face geometry changed')
    doc.verify_source()
    return {'body_occurrences_preserved': occurrences, 'style_bindings_preserved': styles,
            'source_identity_and_placements_exact': True, 'changed_graph_references_exact': True,
            'source_unchanged': True}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--source-sha256', required=True)
    ap.add_argument('--passes', nargs='+', choices=list(PASSES), default=list(PASSES))
    ap.add_argument('--apply', action='store_true', help='apply sharing to a derived in-memory scene only')
    ap.add_argument('--out', type=Path, required=True, help='new small findings report, not a CAD/mesh export')
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()
    if args.out.exists():
        ap.error('output exists')
    if len(args.passes) != len(set(args.passes)):
        ap.error('choose distinct passes')
    direct = args.source.suffix.lower() in {'.stp', '.step'}
    loader = CadDocument.from_step if direct else CadDocument.from_index
    kwargs = {'expected_sha256': args.source_sha256}
    if direct:
        kwargs['workers'] = args.workers
    with loader(args.source, **kwargs) as doc:
        scene = CadScene(doc)
        original = scene
        report = {'source_sha256': doc.source_sha256, 'mode': 'apply-in-memory' if args.apply else 'plan-only',
                  'before': scene.statistics(), 'passes': [], 'source_unchanged': False}
        for name in args.passes:
            plan = plan_pass(scene, name)
            if args.apply:
                scene = apply_plan(scene, plan)
            report['passes'].append({'id': name, **PASSES[name], 'redirect_count': len(plan.redirects),
                'examples': [{'source_id': r.source_id, 'canonical_id': r.canonical_id,
                              'mapped_faces': len(r.face_pairs)} for r in plan.redirects[:20]],
                'skipped_count': len(plan.skipped), 'skipped_examples': plan.skipped[:20]})
            print(f'{name}: {len(plan.redirects)} exact definition redirects, {len(plan.skipped)} skipped', flush=True)
        report['after'] = scene.statistics()
        report['validation'] = validate_equivalence(original, scene)
        doc.verify_source()
        report['source_unchanged'] = True
        report['limitations'] = ['No CAD, mesh or runtime package is exported.',
            'Instances, styles and contacts retain original identity; definition sharing is not placed-triangle reduction.',
            'Consuming the derived reference graph in geometry exporters is separate adapter work.']
        report['producer_sha256'] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                     for name in ('cad_passes.py', 'cad_document.py', 'audit_geometry_duplicates.py')}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write('\n')
        print(json.dumps({'before': report['before'], 'after': report['after']}))


if __name__ == '__main__':
    main()
