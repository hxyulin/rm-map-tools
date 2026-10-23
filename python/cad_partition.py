#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Complete body/shell partitions and inspectable CAD bundles, without geometry edits.

Whole solid bodies and original surface-model shells are indivisible units.
Only the surface-model wrapper's shell list is narrowed for a derived part.
Every source face must belong to exactly one part; unresolved ownership remains
in an explicit remainder. Work grouping never installs new motion bindings.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time

import numpy as np
from cad_document import CadDocument
from cad_components import build_catalog, export_selection
from p21split import Splitter


def compile_partition(document, catalog, policy, *, source_motion=None):
    """Partition selected products completely, including whole source shells.

    Explicit shell IDs or product-local vertex boxes propose ownership. Higher
    priority wins; equal-priority conflicts remain in the fallback group. Bounds
    do not crop shapes and cannot certify curved-surface envelopes or attachment.
    split_source_units bypasses grouping and emits one part per original solid
    or original surface-model shell. Solid cavity shells remain with their body.
    """
    if (policy.get('schema_version') != 1 or policy.get('source_sha256') != document.source_sha256
            or catalog.get('source_sha256') != document.source_sha256):
        raise ValueError('partition policy schema/source SHA-256 mismatch')
    if policy.get('length_unit') != 'millimetre' or set(document.geometry_length_units) != {'.MILLI.,.METRE.'}:
        raise ValueError('partition regions require original millimetre geometry')
    if source_motion and (source_motion.get('schema_version')!=1 or source_motion.get('source_sha256')!=document.source_sha256):
        raise ValueError('prepared source motion schema/source SHA-256 mismatch')
    ix, model = document.index, document.model
    components = {(c['product_id'], c['body_id']): c for c in catalog['components']}
    results, seen_products = [], set()
    for spec in policy['products']:
        product = spec['product_id']
        if product in seen_products or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', spec['name']):
            raise ValueError('duplicate product or unsafe export name')
        seen_products.add(product)
        fallback = spec['fallback_group']
        split_units = spec.get('split_source_units', False)
        if (not isinstance(split_units, bool) or split_units and any(spec.get(k) for k in
                ('body_rules', 'shell_rules', 'body_group_overrides'))):
            raise ValueError('source-unit mode must be boolean and cannot mix with grouping rules')
        rules = spec.get('shell_rules', [])
        bodies = sorted(b for p, b in components if p == product)
        if not bodies:
            raise ValueError('partition product has no catalog body ownership')
        shell_sets = {b: {int(s) for s in ix.refs_of(ix.r(b))} for b in bodies
                      if ix.tname(ix.r(b)) == 'SHELL_BASED_SURFACE_MODEL'}
        for rule in rules:
            if rule['body_id'] not in shell_sets or not rule.get('evidence') or not isinstance(rule['priority'], int):
                raise ValueError('shell rule needs a source surface model, priority and evidence')
            if ('shell_ids' in rule) == ('min_mm' in rule):
                raise ValueError('shell rule needs exactly one explicit or spatial selector')
            if 'shell_ids' in rule:
                if not rule['shell_ids'] or len(set(rule['shell_ids'])) != len(rule['shell_ids']) or not set(rule['shell_ids']) <= shell_sets[rule['body_id']]:
                    raise ValueError('shell rule IDs are not a distinct nonempty source subset')
            else:
                low, high = [np.asarray(rule[k], float) for k in ('min_mm', 'max_mm')]
                if low.shape != (3,) or high.shape != (3,) or not np.isfinite([low, high]).all() or np.any(high <= low):
                    raise ValueError('invalid shell region')
        body_assignments = {}
        for rule in spec.get('body_rules', []):
            selected = rule.get('body_ids', [])
            if (not rule.get('evidence') or not selected or len(selected) != len(set(selected))
                    or not set(selected) <= set(bodies) or set(selected) & set(shell_sets)):
                raise ValueError('body rule needs evidence and distinct original non-surface bodies')
            for body in selected:
                if body in body_assignments:
                    raise ValueError('body is assigned by multiple body rules')
                body_assignments[body] = rule['group']
        groups, units, source_faces = defaultdict(list), [], set()
        changed_groups=set()
        motion_faces=(source_motion or {}).get('face_owners',{})
        motion_default=(source_motion or {}).get('product_defaults',{}).get(str(product))
        for body in bodies:
            row = ix.r(body)
            shells = sorted(shell_sets[body]) if body in shell_sets else [None]
            for shell in shells:
                root = row if shell is None else ix.r(shell)
                if shell is not None and ix.tname(root) not in ('OPEN_SHELL', 'CLOSED_SHELL'):
                    raise ValueError('unsupported source shell type')
                faces = {int(ix.ids[f]) for f in model.body_faces(root)}
                if not faces or source_faces & faces:
                    raise ValueError('partition source units are empty or share face identities')
                source_faces |= faces
                group, reason, matches = fallback, 'unmatched-source-shell', []
                if split_units:
                    group = f'{spec["name"]}/body-{body}' if shell is None else f'{spec["name"]}/shell-{shell}'
                    reason = 'original-solid-body' if shell is None else 'original-surface-shell'
                elif shell is None:
                    original = components[product, body]['group']
                    group = body_assignments.get(body, spec.get('body_group_overrides', {}).get(original, original))
                    reason = 'explicit-body-rule' if body in body_assignments else 'existing-body-component'
                else:
                    low, high, vertices = model.body_bbox(root)
                    for rule in rules:
                        if rule['body_id'] != body or len(faces) in rule.get('exclude_face_counts', []):
                            continue
                        hit = shell in rule['shell_ids'] if 'shell_ids' in rule else (
                            low is not None and np.all(low >= rule['min_mm']) and np.all(high <= rule['max_mm']))
                        if hit:
                            matches.append(rule)
                    if matches:
                        priority = max(r['priority'] for r in matches)
                        best = {r['group'] for r in matches if r['priority'] == priority}
                        if len(best) == 1:
                            group, reason = next(iter(best)), 'explicit-shell' if any('shell_ids' in r for r in matches) else 'spatial-shell-candidate'
                        else:
                            reason = 'equal-priority-shell-conflict'
                if not group.startswith(spec['name']+'/') or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', p) for p in group.split('/')):
                    raise ValueError('unsafe or out-of-product group name')
                unit = {'body_id': body, 'shell_id': shell, 'face_ids': sorted(faces),
                        'group': group, 'assignment': reason,
                        'matched_rules': [r['id'] for r in matches]}
                buckets=defaultdict(list)
                for face in sorted(faces):
                    binding=motion_faces.get(face)
                    if binding and binding['product_id']!=product:
                        raise ValueError('motion face product mismatch')
                    destination=binding['group'] if binding else motion_default or group
                    buckets[destination].append(face)
                for destination,selected in buckets.items():
                    if not destination.startswith(spec['name']+'/') or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*',p) for p in destination.split('/')):
                        raise ValueError('unsafe motion group')
                    changed=len(buckets)>1 or destination!=group
                    if changed:changed_groups.update([group,destination])
                    fragment={**unit,'group':destination,'face_ids':selected,
                              'face_patch':len(buckets)>1,
                              'motion_owners':sorted({motion_faces[f]['motion_owner'] for f in selected
                                                    if f in motion_faces and motion_faces[f]['motion_owner'] is not None})}
                    if changed or any(f in motion_faces for f in selected):fragment['assignment']='reviewed-source-motion'
                    groups[destination].append(fragment)
                    units.append(fragment)
        expected = {int(ix.ids[f]) for b in bodies for f in model.body_faces(ix.r(b))}
        if source_faces != expected:
            raise ValueError('partition dropped or added source faces')
        records = []
        for group, items in sorted(groups.items()):
            face_ids = sorted(f for u in items for f in u['face_ids'])
            record = {'id': group, 'solid_body_ids': sorted(u['body_id'] for u in items if u['shell_id'] is None and not u.get('face_patch')),
                      'shell_ids_by_body': {str(b): sorted(u['shell_id'] for u in items if u['body_id'] == b and not u.get('face_patch'))
                                            for b in sorted({u['body_id'] for u in items if u['shell_id'] is not None and not u.get('face_patch')})},
                      'face_ids_by_body':{str(b):sorted(f for u in items if u['body_id']==b for f in u['face_ids'])
                                          for b in sorted({u['body_id'] for u in items if u.get('face_patch')})},
                      'motion_owners':sorted({o for u in items for o in u.get('motion_owners',[])}),
                      'face_ids': face_ids, 'face_count': len(face_ids),
                      'unit_count': len(items), 'assignment_counts': dict(Counter(u['assignment'] for u in items)),
                      'review_status': 'reviewed-source-motion-ownership; actuator/controller separate' if source_motion and any(u['assignment']=='reviewed-source-motion' for u in items) else 'work-partition-only; attachment/motion not installed'}
            for body in record['face_ids_by_body']:
                record['solid_body_ids']=[b for b in record['solid_body_ids'] if b!=int(body)]
                record['shell_ids_by_body'].pop(body,None)
            signature = spec.get('expected_group_signatures', {}).get(group)
            if signature and group not in changed_groups and (len(record['solid_body_ids']), sum(map(len, record['shell_ids_by_body'].values())), record['face_count']) != tuple(signature):
                raise ValueError('partition group differs from its expected body/shell/face signature')
            records.append(record)
        if set(spec.get('expected_group_signatures', {})) - set(groups) - changed_groups:
            raise ValueError('expected partition group is missing')
        results.append({'name': spec['name'], 'product_id': product, 'source_body_ids': bodies,
                        'source_face_count': len(source_faces), 'source_shell_count': sum(map(len, shell_sets.values())),
                        'groups': records, 'units': units, 'coverage_exactly_once': True,
                        'assignments': dict(Counter(u['assignment'] for u in units))})
    document.verify_source()
    return {'schema_version': 1, 'source_sha256': document.source_sha256,
            'source_unchanged': True, 'products': results,
            'limitations': ['Original body/shell units or explicit motion-owned face patches; no face clipping or geometric edits.',
                'Spatial groups are work proposals, not attachment, collision or motion authority.',
                'Shared surface-model wrappers can appear in several files with disjoint shell lists.',
                'A fallback group retains all unmatched or conflicting source shells.']}


def _selection(catalog, product, group):
    keys = set(group['solid_body_ids']) | {int(b) for b in group['shell_ids_by_body']} | {int(b) for b in group.get('face_ids_by_body',{})}
    components = [c for c in catalog['components'] if c['product_id'] == product and c['body_id'] in keys]
    ids = {c['id'] for c in components}
    return {'source_sha256': catalog['source_sha256'], 'selector': group['id'],
            'coordinate_contract': catalog['coordinate_contract'], 'components': components,
            'occurrences': [o for o in catalog['occurrences'] if o['component_id'] in ids],
            'partition_source_face_ids': group['face_ids'], 'review_status': group['review_status']}


def _pack_step(directory):
    path = directory/'source.step'
    target = directory/'source.step.gz'
    with path.open('rb') as source, target.open('xb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0, compresslevel=6) as packed:
            shutil.copyfileobj(source, packed)
    metadata_path = directory/'selection.json'
    metadata = json.loads(metadata_path.read_text())
    metadata.update(work_step_file=target.name, work_step_compression='gzip',
                    compressed_step_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False)+'\n')
    path.unlink()


def _validate_mesh_stats(stats):
    """Accept only explicitly measured zero-area native faces without triangles.

    These faces remain in exact STEP; they have no renderable area. Missing
    nonzero-area faces and unaccounted degeneracy always fail bundle export.
    """
    if stats.get('unmeshed_faces'):
        raise ValueError('incomplete native tessellation')
    details = stats.get('degenerate_details', [])
    if (stats.get('degenerate_faces', 0) != len(details)
            or any(not np.isfinite(d['area_mm2']) or abs(d['area_mm2']) >= 1e-8 for d in details)):
        raise ValueError('native degenerate faces lack verified zero-area measurements')


def export_bundle(document, catalog, partition, out, *, lin_mm=.4, ang_rad=.25):
    """Export complete STEP/GLB assemblies and every disjoint component atomically.

    STEP files are gzip-packed after validation to avoid duplicating enormous
    repeated layer lists on disk. GLB is a tessellated RGB inspection derivative;
    exact STEP geometry/style records and source-face partitions remain authority.
    """
    from validate_parts import read_part
    from export_step_elements import shape_counts
    from mesh_parts import tessellate
    from export_field_package import GlbWriter
    import provenance
    if partition['source_sha256'] != document.source_sha256 or catalog['source_sha256'] != document.source_sha256:
        raise ValueError('bundle source mismatch')
    if lin_mm <= 0 or ang_rad <= 0 or not np.isfinite([lin_mm, ang_rad]).all():
        raise ValueError('positive finite tessellation tolerances required')
    out = Path(out)
    if out.exists():
        raise ValueError('bundle output exists')
    out.parent.mkdir(parents=True, exist_ok=True)
    splitter = Splitter(document.index, document.model)
    with tempfile.TemporaryDirectory(dir=out.parent) as temporary:
        stage = Path(temporary)/'bundle'
        stage.mkdir()
        shutil.copyfile(Path(__file__).resolve().parents[1]/'NOTICE.md', stage/'NOTICE.md')
        manifest = {'schema_version': 1, 'source_sha256': document.source_sha256,
                    'geometry_units': 'metres in GLB, original millimetres in STEP',
                    'preview_tessellation': {'linear_mm': lin_mm, 'angular_rad': ang_rad},
                    'coverage_exactly_once': True, 'products': []}
        for product in partition['products']:
            name, pid = product['name'], product['product_id']
            print(f'Complete CAD export: {name}', flush=True)
            folder = stage/name
            folder.mkdir()
            body_ids = set(product['source_body_ids'])
            full_components = [c for c in catalog['components'] if c['product_id'] == pid and c['body_id'] in body_ids]
            ids = {c['id'] for c in full_components}
            occurrences = [o for o in catalog['occurrences'] if o['component_id'] in ids]
            full_selection = {'source_sha256': catalog['source_sha256'], 'selector': name,
                              'coordinate_contract': catalog['coordinate_contract'],
                              'components': full_components, 'occurrences': occurrences}
            export_selection(document, full_selection, folder/'full', splitter=splitter)
            _pack_step(folder/'full')
            # Keep product vertices local; a common node rotation makes inspection Y-up.
            rotation = np.eye(4)
            rotation[:3, :3] = np.array([[1.,0,0],[0,0,1],[0,-1,0]]) @ np.asarray(occurrences[0]['source_world_matrix'])[:3,:3]
            asset = provenance.glb_asset('cad_partition.py', document.source_path, document.source_sha256,
                source_product_id=pid,
                frame='product-local metres with common source-arena-to-Y-up node rotation',
                mesh_to_original_face_map='unavailable; exact source face sets are in partition.json')
            full_writer = GlbWriter(name, asset)
            report = {k: v for k,v in product.items() if k != 'units'}
            report['groups'] = []
            for group in product['groups']:
                started = time.perf_counter()
                relative = Path('components')/group['id'].split('/',1)[1]
                directory = folder/relative
                selection = _selection(catalog, pid, group)
                shell_map = {int(b): values for b, values in group['shell_ids_by_body'].items()}
                export_selection(document, selection, directory, shell_ids_by_body=shell_map, face_ids_by_body={int(b):ids for b,ids in group.get('face_ids_by_body',{}).items()}, splitter=splitter)
                native, reader, error = read_part(str(directory/'source.step'))
                if error:
                    raise ValueError(error)
                counts = list(shape_counts(native))
                if counts[1] != group['face_count'] or counts[0] != len(group['solid_body_ids']):
                    raise ValueError(f'Native import altered part topology: {group["id"]}: {counts}')
                stats = {}
                mesh = tessellate(native, lin_mm, ang_rad, stats=stats)
                if mesh is None:
                    raise ValueError(f'Incomplete native tessellation: {group["id"]}: {stats}')
                _validate_mesh_stats(stats)
                positions, triangles, colors, keys = mesh
                color_keys = [keys[int(i)] for i in colors]
                extras = {'cad_partition': {'source_sha256': document.source_sha256,
                          'product_id': pid, 'group': group['id'], 'solid_body_ids': group['solid_body_ids'],
                          'shell_ids_by_body': group['shell_ids_by_body'], 'face_ids_by_body':group.get('face_ids_by_body',{}), 'source_face_count': group['face_count']}}
                writer = GlbWriter(group['id'], asset)
                writer.add_node(group['id'], positions/1000, triangles, color_keys, matrix=rotation, extras=extras)
                writer.write(directory/'visual.glb')
                full_writer.add_node(group['id'], positions/1000, triangles, color_keys, matrix=rotation, extras=extras)
                _pack_step(directory)
                record = {**group, 'directory': str(relative), 'native_solids': counts[0],
                          'native_faces': counts[1], 'triangles': len(triangles), 'tessellation_stats': stats,
                          'elapsed_seconds': time.perf_counter()-started}
                report['groups'].append(record)
                print(f'  {group["id"]}: {counts[0]} solids, {counts[1]} faces, {len(triangles)} triangles', flush=True)
                del native, reader, mesh, writer
            full_writer.write(folder/'full'/'visual.glb')
            if sum(g['native_faces'] for g in report['groups']) != product['source_face_count']:
                raise ValueError('Native part face coverage differs from complete source product')
            report['full_triangles'] = sum(g['triangles'] for g in report['groups'])
            report['full_visual'] = 'full/visual.glb'
            report['full_step'] = 'full/source.step.gz'
            manifest['products'].append(report)
        document.verify_source()
        (stage/'partition.json').write_text(json.dumps(partition, indent=2)+'\n')
        manifest['files_sha256'] = {str(p.relative_to(stage)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(stage.rglob('*')) if p.is_file()}
        (stage/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
        stage.rename(out)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--components', type=Path, required=True)
    parser.add_argument('--motion-profile', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--export', action='store_true', help='write complete CAD/GLB bundle, otherwise partition JSON only')
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())
    component_policy = json.loads(args.components.read_text())
    profile = json.loads(args.motion_profile.read_text())
    region = component_policy.get('region_plan')
    region_plan = None
    if region:
        path = args.components.parent/region['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != region['sha256']:
            raise ValueError('component region pin mismatch')
        region_plan = json.loads(path.read_text())
    loader = CadDocument.from_index if args.source.suffix == '.npz' else CadDocument.from_step
    with loader(args.source, expected_sha256=policy['source_sha256']) as document:
        catalog = build_catalog(document, component_policy, profile, region_plan)
        result = compile_partition(document, catalog, policy)
        result['inputs_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in (args.policy,args.components,args.motion_profile)}
        result['producer_sha256'] = {p: hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest()
                                    for p in ('cad_partition.py','cad_components.py','p21split.py','p21model.py',
                                              'cad_document.py','mesh_parts.py','export_field_package.py','validate_parts.py','provenance.py')}
        if args.export:
            export_bundle(document, catalog, result, args.out)
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open('x') as stream:
                json.dump(result,stream,indent=2)
                stream.write('\n')
    print(json.dumps([{'product':p['name'],'groups':len(p['groups']),'faces':p['source_face_count'],
                       'shells':p['source_shell_count'],'assignments':p['assignments']} for p in result['products']],indent=2))


if __name__ == '__main__':
    main()
