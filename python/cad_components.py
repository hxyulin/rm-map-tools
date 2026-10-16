#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-owned component catalog and exact whole-body work selections.

A component is one original body in its product context. Manual groups only
organize those leaves. Placed instances retain full occurrence paths and source
matrices; changing a group never changes source geometry, style or motion.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import tempfile

from cad_document import CadDocument
from cad_passes import CadScene
from p21model import BODY_TYPES
from review_cad_layers import review_layers, validate_profile


def build_catalog(document, policy, motion_profile, region_plan=None):
    """Partition every source body into exactly one leaf, with validated manual groups."""
    if policy.get('schema_version') != 1 or policy.get('source_sha256') != document.source_sha256:
        raise ValueError('component policy schema/source SHA-256 mismatch')
    motion = validate_profile(document, motion_profile)
    ix, model = document.index, document.model
    owned = defaultdict(set)
    for body, representation in model.bodies:
        product = model.rep_product.get(representation)
        if product is None:
            raise ValueError('body representation has no product owner')
        owned[int(ix.ids[product])].add(int(ix.ids[body]))
    source_bodies = {int(ix.ids[b]) for b in ix.rows_of(*BODY_TYPES)}
    if set().union(*owned.values()) != source_bodies:
        raise ValueError('source body ownership is incomplete')
    names = policy['product_names']
    product_ids = {int(ix.ids[p]) for p in model.product_name}
    if set(map(int, names)) != product_ids or len(set(names.values())) != len(names):
        raise ValueError('policy must name every product uniquely')
    if any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', n) for n in names.values()):
        raise ValueError('product names must be stable lowercase slugs')
    region_results = {}
    if any(g.get('review_status') == 'spatial-candidate' for g in policy.get('groups', [])):
        if region_plan is None:
            raise ValueError('spatial candidate groups require their region plan')
        from audit_component_regions import audit_regions
        region_results = {r['id']: r for r in audit_regions(document, region_plan, motion_profile)['regions']}
    manual = defaultdict(list)
    for group in policy.get('groups', []):
        product = group['product_id']
        path = group['path']
        if product not in owned or not group.get('evidence') or not group['body_ids']:
            raise ValueError('manual group needs a known product, nonempty bodies and evidence')
        if not path or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', part) for part in path):
            raise ValueError('manual group path must contain safe slugs')
        if path[0] == 'other-bodies':
            raise ValueError('other-bodies is reserved for automatic remainder')
        status = group.get('review_status', 'existing-binding')
        if status not in ('existing-binding', 'spatial-candidate', 'source-identity'):
            raise ValueError('unknown group review status')
        if status == 'spatial-candidate':
            region = region_results.get(group.get('region_id'))
            if (region is None or not region['expected_membership_matches']
                    or region['product_id'] != product
                    or set(region['contained_body_ids']) != set(group['body_ids'])):
                raise ValueError('spatial group disagrees with its source region audit')
        manual[product].append(group)
    components, groups = [], []
    for product in sorted(owned):
        claimed, paths = set(), set()
        for group in manual[product]:
            selected = set(group['body_ids'])
            path = tuple(group['path'])
            if len(selected) != len(group['body_ids']) or not selected <= owned[product] or selected & claimed:
                raise ValueError('manual groups overlap or select a body outside their product')
            if any(path[:len(other)] == other or other[:len(path)] == path for other in paths):
                raise ValueError('manual group paths overlap')
            assigned = {motion.get((product, b), ('unknown', 'unknown')) for b in selected}
            # A working group may be an assembly, but never present it as one rigid owner.
            groups.append({'id': names[str(product)]+'/'+ '/'.join(path),
                           'product_id': product, 'body_ids': sorted(selected),
                           'evidence': group['evidence'], 'kind': 'manual-whole-body-group',
                           'review_status': group.get('review_status', 'existing-binding'),
                           'single_reviewed_motion_owner': len(assigned) == 1 and 'unknown' not in next(iter(assigned))})
            paths.add(path)
            claimed |= selected
        remainder = owned[product]-claimed
        if remainder:
            groups.append({'id': names[str(product)]+'/other-bodies', 'product_id': product,
                           'body_ids': sorted(remainder), 'evidence': ['Unassigned original source bodies; no semantic role inferred.'],
                           'kind': 'source-remainder', 'review_status': 'unreviewed', 'single_reviewed_motion_owner': False})
        for body in sorted(owned[product]):
            parent = next((g['id'] for g in groups if g['product_id'] == product and body in g['body_ids']), None)
            role, owner = motion.get((product, body), ('unknown', 'unknown'))
            components.append({'id': f'p{product}.b{body}', 'product_id': product,
                               'body_id': body, 'group': parent, 'motion': role, 'motion_owner': owner,
                               'physical_role': 'unknown', 'appearance_control': 'unknown',
                               'group_review_status': next(g['review_status'] for g in groups if g['id'] == parent),
                               'source_faces': len(model.body_faces(ix.r(body))), 'whole_body_layer_ids': []})
    # Whole-body layers annotate existing leaves, never determine coverage.
    qualified = review_layers(document, motion_profile)
    layer_annotations = []
    for group in qualified['groups']:
        if group['scope'] != 'complete_single_body':
            continue
        body = group['body_coverage'][0]['body_id']
        layer_annotations.extend(group['layers'])
        for component in components:
            if component['body_id'] == body:
                component['whole_body_layer_ids'] = [l['source_id'] for l in group['layers']]
    component_by_key = {(c['product_id'], c['body_id']): c['id'] for c in components}
    assemblies = []
    edges = {}
    for product in sorted(model.product_name):
        children = []
        for edge, child in model.children.get(product, []):
            if child is None or edge not in document.transforms:
                raise ValueError('assembly child/placement unresolved')
            identity = int(ix.ids[edge])
            child_id = int(ix.ids[child])
            edges[identity] = child_id
            children.append({'occurrence_id': identity, 'product_id': child_id,
                             'strings': list(document.entity(identity).strings),
                             'source_local_matrix': document.transforms[edge].tolist()})
        pid = int(ix.ids[product])
        assemblies.append({'product_id': pid, 'name': names[str(pid)],
                           'source_strings': list(document.entity(pid).strings), 'children': children})
    occurrences, identities = [], set()
    for occurrence in CadScene(document).occurrences():
        key = occurrence.product_id, occurrence.source_body_id
        identity = (occurrence.root_product_id, occurrence.occurrence_path, *key)
        if identity in identities:
            raise ValueError('duplicate placed component identity')
        identities.add(identity)
        occurrences.append({'component_id': component_by_key[key],
                            'root_product_id': occurrence.root_product_id,
                            'occurrence_path': list(occurrence.occurrence_path),
                            'ancestor_product_ids': [occurrence.root_product_id]+[edges[o] for o in occurrence.occurrence_path],
                            'source_world_matrix': occurrence.matrix.tolist()})
    visited = {o['component_id'] for o in occurrences}
    if visited != {c['id'] for c in components}:
        raise ValueError('component definitions exist outside the placed assembly')
    document.verify_source()
    return {'schema_version': 1, 'mode': 'whole-body-component-catalog',
            'source_sha256': document.source_sha256, 'source_unchanged': True,
            'coordinate_contract': {'geometry_frame': 'original product frame',
                                    'world_matrix_maps': 'product local to original source assembly frame',
                                    'length_units': document.geometry_length_units},
            'summary': {'source_body_definitions': len(source_bodies), 'component_definitions': len(components),
                        'placed_component_occurrences': len(occurrences), 'assembly_definitions': len(assemblies),
                        'manual_groups': sum(g['kind'] == 'manual-whole-body-group' for g in groups),
                        'motion_definitions': dict(Counter(c['motion'] for c in components))},
            'assemblies': assemblies, 'groups': groups, 'components': components,
            'occurrences': occurrences, 'whole_body_layers': layer_annotations,
            'limitations': ['Groups only organize original body definitions; no face or geometry edits.',
                'Matrices retain source units and axes. No transform baking or recentering.',
                'Shared definitions retain distinct placed occurrences and per-source styles.',
                'A source body may contain fused structural, artwork and internal detail.',
                'Unknown function/motion/appearance control remain unknown.']}


def select_components(catalog, selector):
    """Select an assembly subtree, manual group/prefix or stable component ID.

    Assembly selections filter placed occurrence ancestry. A shared definition
    placed elsewhere is not accidentally included with its other occurrences.
    """
    assembly = next((a for a in catalog['assemblies'] if a['name'] == selector), None)
    if assembly is not None:
        occurrences = [o for o in catalog['occurrences'] if assembly['product_id'] in o['ancestor_product_ids']]
    else:
        ids = {c['id'] for c in catalog['components'] if c['id'] == selector
               or c['group'] == selector or c['group'].startswith(selector+'/')}
        occurrences = [o for o in catalog['occurrences'] if o['component_id'] in ids]
    if not occurrences:
        raise ValueError('selector matches no placed components')
    ids = {o['component_id'] for o in occurrences}
    return {'source_sha256': catalog['source_sha256'], 'selector': selector,
            'coordinate_contract': catalog.get('coordinate_contract', {}),
            'components': [c for c in catalog['components'] if c['id'] in ids], 'occurrences': occurrences}


def export_selection(document, selection, out, *, shell_ids_by_body=None, face_ids_by_body=None, splitter=None):
    """Export one selected product's original bodies to STEP plus exact placement metadata.

    The STEP remains in its original product frame. Multiple placed copies are
    carried in selection.json; they are not baked into the geometry. Select a
    narrower group when an assembly spans multiple product coordinate frames.
    Explicit face_ids_by_body exports original face patches as open surfaces;
    it preserves face geometry/styles but deliberately gives up solid topology.
    Such patches are inspection derivatives, not valid solid collision bodies.
    """
    from p21split import Splitter
    products = {c['product_id'] for c in selection['components']}
    if selection['source_sha256'] != document.source_sha256 or len(products) != 1:
        raise ValueError('STEP work selection must have one product frame and matching source SHA')
    out = Path(out)
    if out.exists():
        raise ValueError('output exists')
    bodies = {c['body_id'] for c in selection['components']}
    product = next(iter(products))
    owners = {int(document.index.ids[b]) for b, rep in document.model.bodies
              if document.model.rep_product.get(rep) == document.index.r(product)}
    if not bodies or not bodies <= owners:
        raise ValueError('work selection body ownership differs from source')
    shell_ids_by_body = shell_ids_by_body or {}
    face_ids_by_body = face_ids_by_body or {}
    if not set(face_ids_by_body) <= bodies:
        raise ValueError('face selection names an unselected body')
    if not set(shell_ids_by_body) <= bodies:
        raise ValueError('shell selection names an unselected body')
    splitter = splitter or Splitter(document.index, document.model)
    if splitter.ix is not document.index or splitter.m is not document.model:
        raise ValueError('splitter belongs to another source document')
    mask, rewritten = splitter.closure_products([document.index.r(product)], body_ids=bodies,
                                               shell_ids_by_body=shell_ids_by_body, face_ids_by_body=face_ids_by_body)
    actual = {int(document.index.ids[b]) for b in document.index.rows_of(*BODY_TYPES) if mask[b]}
    if actual != bodies:
        raise ValueError('STEP closure changed the selected body set')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp)/'component'
        stage.mkdir()
        splitter.write_closure(mask, rewritten, stage/'source.step')
        # Reparse without importing/healing: selected geometry records must be byte-identical.
        with CadDocument.from_step(stage/'source.step', workers=1) as check:
            selected_rows = [document.index.r(b) for b in bodies if b not in shell_ids_by_body and b not in face_ids_by_body]
            selected_rows.extend(document.index.r(s) for values in shell_ids_by_body.values() for s in values)
            selected_rows.extend(document.index.r(f) for values in face_ids_by_body.values() for f in values)
            from p21split import forward_closure
            import numpy as np
            geometry = forward_closure(document.index, selected_rows, np.zeros(document.index.n, bool))
            expected_faces = {int(document.index.ids[r]) for r in np.flatnonzero(geometry)
                              if document.index.tname(int(r)) == 'ADVANCED_FACE'}
            if expected_faces != {int(check.index.ids[r]) for r in check.index.rows_of('ADVANCED_FACE')}:
                raise ValueError('export changed the selected source face set')
            # Block original wrapper traversal while retaining parent-level style bindings.
            for body in set(shell_ids_by_body) | set(face_ids_by_body):
                geometry[document.index.r(body)] = True
            for row in rewritten:
                if document.index.tname(row) in ('OPEN_SHELL', 'CLOSED_SHELL'):
                    geometry[row] = True
            style_rows = [style for row in np.flatnonzero(geometry)
                          for style in document.model.style_of_target.get(int(row), ())]
            preserved = forward_closure(document.index, style_rows, geometry.copy())
            for row in np.flatnonzero(preserved):
                source_id = int(document.index.ids[row])
                expected = rewritten[row] if row in rewritten else document.entity(source_id).raw
                if check.index.r(source_id) < 0 or check.entity(source_id).raw != expected:
                    raise ValueError('export changed a source geometry or style record')
            if any(check.index.r(int(ref)) < 0 for ref in check.index.refs):
                raise ValueError('export has dangling references')
        document.verify_source()
        metadata = {**selection, 'work_step_sha256': hashlib.sha256((stage/'source.step').read_bytes()).hexdigest(),
                    'geometry_and_style_records_preserved': True,
                    'selected_source_shell_ids': {str(b): sorted(ids) for b, ids in shell_ids_by_body.items()},
                    'rewritten_surface_model_body_ids': sorted(set(shell_ids_by_body) | set(face_ids_by_body)),
                    'selected_source_face_ids_by_body': {str(b): sorted(ids) for b, ids in face_ids_by_body.items()},
                    'face_patch_topology': 'open surfaces; original source solid remains authority' if face_ids_by_body else None}
        (stage/'selection.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False)+'\n')
        stage.rename(out)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='original STEP or optional index cache')
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--motion-profile', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='new catalog JSON, or new work directory with --export-step')
    parser.add_argument('--select', help='assembly name, manual group/prefix, or stable component ID')
    parser.add_argument('--export-step', action='store_true')
    args = parser.parse_args()
    if args.out.exists() or args.export_step and not args.select:
        parser.error('output must be new; --export-step requires --select')
    policy = json.loads(args.policy.read_text())
    profile = json.loads(args.motion_profile.read_text())
    region_plan = None
    region_evidence = policy.get('region_plan')
    if region_evidence:
        region_path = args.policy.parent / region_evidence['path']
        if hashlib.sha256(region_path.read_bytes()).hexdigest() != region_evidence['sha256']:
            raise ValueError('component region plan SHA-256 mismatch')
        region_plan = json.loads(region_path.read_text())
    loader = CadDocument.from_index if args.source.suffix == '.npz' else CadDocument.from_step
    with loader(args.source, expected_sha256=policy['source_sha256']) as document:
        catalog = build_catalog(document, policy, profile, region_plan)
        catalog['producer_sha256'] = {p: hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest()
                                     for p in ('cad_components.py', 'cad_document.py', 'cad_passes.py',
                                               'review_cad_layers.py', 'audit_semantic_evidence.py',
                                               'p21model.py', 'p21index.py', 'mesh_parts.py', 'p21split.py', 'audit_step.py',
                                               'audit_component_regions.py')}
        catalog['policy_sha256'] = hashlib.sha256(args.policy.read_bytes()).hexdigest()
        catalog['region_plan_sha256'] = region_evidence['sha256'] if region_evidence else None
        catalog['motion_profile_sha256'] = hashlib.sha256(args.motion_profile.read_bytes()).hexdigest()
        result = select_components(catalog, args.select) if args.select else catalog
        if args.select:
            result['catalog_provenance'] = {k: catalog[k] for k in ('producer_sha256', 'policy_sha256', 'motion_profile_sha256', 'region_plan_sha256')}
        if args.export_step:
            export_selection(document, result, args.out)
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x') as stream:
                json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write('\n')
    print(json.dumps(catalog['summary'] if not args.select else
                     {'selector': args.select, 'components': len(result['components']),
                      'occurrences': len(result['occurrences'])}, indent=2))


if __name__ == '__main__':
    main()
