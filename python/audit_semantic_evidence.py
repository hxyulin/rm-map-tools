# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Inventory semantic evidence without turning names or colours into physics rules.

Motion and physical/decoration roles are separate, unresolved axes. Source
assembly ownership is exact; name matches are review hints only. Layer lists
are compared exactly and analyzed once, preserving every original layer name.
"""
from collections import Counter, defaultdict
import hashlib
import re

import numpy as np
from p21model import BODY_TYPES, STR_RE, decode_p21

HINTS = {
    'motion': r'dynamic|movable|动态|运动|rotor|rotating|moving|slider|hinge|revolute|prismatic|旋转|转子|滑动|活动',
    'fixed_structure': r'(?:^|_)static(?:_|$)|fixed|固定|静态',
    'terrain': r'floor|ground|ramp|platform|wall|地面|高地|坡|围墙|公路|路段',
    'decoration': r'paint|decor|decal|silk|marking|丝印|贴纸|喷绘|涂装|标线',
    'lighting': r'led|light.guide|light.bar|灯|导光',
    'equipment': r'armor|base|outpost|rune|dart|fan|装甲|基地|前哨|能量|飞镖|风机|堡垒|资源',
    'colour': r'^COLOR\d+(?:_\d+)*$',
}
# Actual kinematics type tokens, not geometrical SURFACE_OF_REVOLUTION or
# MECHANICAL_CONTEXT (which describe geometry/product context, not movement).
MOTION_TYPE = re.compile(r'KINEMATIC|ACTUAT|MECHANISM|(?:^|_)JOINT(?:_|$)|'
                         r'REVOLUTE_PAIR|PRISMATIC_PAIR|CYLINDRICAL_PAIR|'
                         r'SPHERICAL_PAIR|PLANAR_PAIR|GEAR_PAIR|RACK_AND_PINION_PAIR|'
                         r'SCREW_PAIR|UNIVERSAL_PAIR|ROLLING.*PAIR|SLIDING.*PAIR')
TYPE_TOKEN = re.compile(rb'\b([A-Z][A-Z_0-9]*)\s*\(')


def hints(text):
    """Return non-authoritative review categories, never an assigned runtime role."""
    return [name for name, pattern in HINTS.items() if re.search(pattern, text.strip(), re.I)]


def motion_records(ix):
    """Find explicit motion-family types, including components of complex records."""
    records = []
    for kind in ix.typenames:
        if kind != 'CPLX' and not MOTION_TYPE.search(kind):
            continue
        for row in ix.rows_of(kind):
            # Remove strings and comments before scanning complex type names.
            raw = re.sub(rb'/\*.*?\*/', b'', STR_RE.sub(b"''", ix.text(int(row))), flags=re.S)
            types = sorted({t.decode() for t in TYPE_TOKEN.findall(raw)
                            if MOTION_TYPE.search(t.decode())})
            if types:
                records.append({'source_id': int(ix.ids[row]), 'types': types})
    return records


def semantic_evidence(ix, model):
    """Report layers, assembly entities, appearance metadata and unresolved roles.

    References to faces/bodies are resolved through source topology. Curves,
    shells and styled-item targets retain their types but aren't guessed into
    body ownership. No absence of metadata is interpreted as static geometry.
    """
    type_counts = Counter()
    counts = np.bincount(ix.types, minlength=len(ix.typenames))
    type_counts.update({n: int(counts[i]) for i, n in enumerate(ix.typenames) if counts[i]})
    body_owners = defaultdict(set)
    face_bodies = defaultdict(set)
    for body, representation in model.bodies:
        product = model.rep_product.get(representation)
        if product is not None:
            body_owners[int(body)].add(int(product))
    for body in ix.rows_of(*BODY_TYPES):
        for face in model.body_faces(int(body)):
            face_bodies[int(face)].add(int(body))

    memberships = []
    buckets = defaultdict(list)
    nonempty_descriptions = 0
    target_references = 0
    hint_counts = Counter()
    shared_groups = {}
    for row in ix.rows_of('PRESENTATION_LAYER_ASSIGNMENT'):
        row = int(row)
        strings = [decode_p21(s) for s in STR_RE.findall(ix.text(row))]
        name, description = (strings+['', ''])[:2]
        refs = ix.refs_of(row)
        span_key = ix.layer_membership_key(row) if hasattr(ix, 'layer_membership_key') else None
        group = shared_groups.get(span_key) if span_key is not None else None
        if group is None:
            digest = hashlib.sha256(refs.tobytes()).hexdigest()
            group = next((memberships[i] for i in buckets[digest]
                          if np.array_equal(memberships[i]['_refs'], refs)), None)
        if group is None:
            group = {'membership_group': len(memberships), 'membership_sha256': digest,
                     '_refs': refs, 'layers': []}
            buckets[digest].append(len(memberships))
            memberships.append(group)
        if span_key is not None:
            shared_groups[span_key] = group
        matched = hints(name+' '+description)
        hint_counts.update(matched)
        nonempty_descriptions += bool(description)
        target_references += len(refs)
        group['layers'].append({'source_id': int(ix.ids[row]), 'name': name,
                                'description': description, 'name_hints': matched})

    coverage = np.zeros(ix.n, dtype=np.int32)
    for group in memberships:
        refs = group.pop('_refs')
        rows = np.array([ix.r(int(r)) for r in refs], dtype=np.int64)
        resolved = np.unique(rows[rows >= 0])
        coverage[resolved] += len(group['layers'])
        bodies = set()
        for row in resolved:
            if ix.tname(int(row)) in BODY_TYPES:
                bodies.add(int(row))
            bodies.update(face_bodies.get(int(row), ()))
        products = set().union(*(body_owners[b] for b in bodies)) if bodies else set()
        target_types = Counter(ix.tname(int(r)) for r in rows if r >= 0)
        appearance_only = bool(target_types) and not (rows < 0).any() and all(
            'STYLE' in kind or 'COLOUR' in kind or 'MATERIAL' in kind for kind in target_types)
        group.update(all_targets_are_appearance_records=bool(appearance_only),
                     target_references=len(refs), unresolved_references=int((rows < 0).sum()),
                     target_types=dict(target_types),
                     referenced_body_ids=sorted(int(ix.ids[b]) for b in bodies),
                     referenced_owner_product_ids=sorted(int(ix.ids[p]) for p in products),
                     motion='unknown', physical_role='unknown',
                     interpretation='Layer membership and name hints only; no role assignment.')

    products = []
    for product in sorted(model.product_name):
        strings = [decode_p21(s) for s in STR_RE.findall(ix.text(product))]
        products.append({'product_id': int(ix.ids[product]), 'strings': strings,
                         'name_hints': hints(' '.join(strings)),
                         'direct_body_ids': sorted(int(ix.ids[b]) for b, owners in body_owners.items()
                                                   if product in owners)})
    occurrences = []
    for row, (parent, child) in sorted(model.nauo.items()):
        strings = [decode_p21(s) for s in STR_RE.findall(ix.text(row))]
        occurrences.append({'occurrence_id': int(ix.ids[row]),
                            'parent_product_id': int(ix.ids[parent]) if parent is not None else None,
                            'child_product_id': int(ix.ids[child]) if child is not None else None,
                            'strings': strings, 'name_hints': hints(' '.join(strings)),
                            'motion': 'unknown', 'physical_role': 'unknown'})
    motion = motion_records(ix)
    face_rows = ix.rows_of('ADVANCED_FACE')
    hits = coverage[face_rows]
    return {
        'summary': {'products': len(products), 'assembly_occurrences': len(occurrences),
                    'body_definitions': len(ix.rows_of(*BODY_TYPES)),
                    'layers': sum(len(g['layers']) for g in memberships),
                    'unique_ordered_memberships': len(memberships),
                    'layer_target_references': target_references,
                    'nonempty_layer_descriptions': nonempty_descriptions,
                    'layer_name_hints': dict(hint_counts),
                    'explicit_motion_records': len(motion),
                    'source_faces': len(face_rows), 'layer_covered_faces': int((hits > 0).sum()),
                    'faces_in_multiple_layers': int((hits > 1).sum()),
                    'confirmed_dynamic_bodies': 0, 'confirmed_static_bodies': 0,
                    'confirmed_decoration_bodies': 0},
        'motion_evidence': motion,
        'appearance_evidence': {
            'style_target_types': dict(Counter(ix.tname(int(value[0]))
                                               for value in model.styled.values())),
            'material_types': {n: c for n, c in type_counts.items() if 'MATERIAL' in n},
            'texture_types': {n: c for n, c in type_counts.items() if 'TEXTURE' in n},
            'transparency_types': {n: c for n, c in type_counts.items() if 'TRANSPAREN' in n},
            'appearance_only_membership_groups': sum(g['all_targets_are_appearance_records']
                                                     for g in memberships)},
        'source_type_counts': dict(sorted(type_counts.items())),
        'products': products, 'assembly_occurrences': occurrences,
        'layer_memberships': memberships,
        'policy': [
            'Unknown motion never means static. Rest-pose transforms do not define motion.',
            'Kinematic record detection alone does not bind body motion; binding needs a separate resolver.',
            'Products/occurrences are source assembly entities, not inferred gameplay entities.',
            'Colour, lighting and decoration names are hints, not collision-exclusion masks.',
            'Presentation/style records are appearance metadata, not geometric decal bodies.',
            'Body/face layer coverage is exact; curve, shell and styled-item ownership is not inferred.',
            'Runtime roles require reviewed, source-hash-qualified occurrence/body bindings.'],
    }
