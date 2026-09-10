# SPDX-License-Identifier: MIT OR Apache-2.0
"""Add semantic names, joint frames and collision layers without tessellating CAD.

export_semantics.py PACKAGE --rules RULES.json --out NEW_DIRECTORY
export_semantics.py PACKAGE --catalog catalog.json

Rules select exact node names (and occurrence for duplicates), never colors or
bounding boxes. Unknown source meshes are recorded in the sidecar audit.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

from gltf_scene import local_matrix, read_glb, scene_nodes, write_glb

ROLES = {'assembly', 'static', 'rotor', 'arm', 'armor_module', 'armor_housing',
         'led_surface', 'rune_target', 'dart_detector', 'guiding_light',
         'status_indicator', 'protective_shield', 'decoration', 'gate', 'platform',
         'carriage', 'rail', 'target_frame', 'unclassified'}
LAYERS = {
    'reconstruction': {'visible_by_default': True, 'purpose': 'Authored approximate geometry and reused parts filling gaps in source CAD; provenance and collision accuracy must remain explicit.'},
    'geometry': {'visible_by_default': True, 'purpose': 'Physical housings, structures and moving parts.'},
    'markings': {'visible_by_default': True, 'purpose': 'Text, logos, paint sheets and visual decals; classification does not disable collision.'},
    'lights': {'visible_by_default': True, 'purpose': 'LED and other luminous surfaces, controlled by semantic channels.'},
    'collision': {'visible_by_default': False, 'purpose': 'Optional collision helper geometry for inspection; never inferred from thin surfaces.'},
    'debug': {'visible_by_default': False, 'purpose': 'Joint axes, target-frame markers and other authored diagnostic geometry.'},
}
FUNCTIONS = {'armor_bar', 'rune_target', 'rune_activated_outline', 'rune_progress',
             'center_logo', 'dart_guidance', 'status'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'path outside package: {name}')
    return path


def finite_vector(value, size, name):
    a = np.asarray(value, float)
    if a.shape != (size,) or not np.isfinite(a).all():
        raise ValueError(f'invalid {name}')
    return a


def validate_metadata(meta):
    if not isinstance(meta.get('id'), str) or not meta['id']:
        raise ValueError('metadata requires a stable id')
    roles = meta.get('roles', [])
    if not roles or set(roles) - ROLES:
        raise ValueError(f'invalid roles for {meta["id"]}')
    if 'armor' in meta:
        armor = meta['armor']
        if armor.get('family') not in {'robot', 'outpost', 'base', 'dart_detection', 'unknown'}:
            raise ValueError('invalid armor family')
        if armor.get('size_class') not in {'small', 'large', 'custom', 'unknown'}:
            raise ValueError('invalid armor size_class')
    if 'led' in meta:
        if 'led_surface' not in roles or meta['led'].get('function') not in FUNCTIONS or not meta['led'].get('channel'):
            raise ValueError('LED requires surface role, function and channel')
    if 'supported_modes' in meta and (not meta['supported_modes'] or set(meta['supported_modes']) - {'small', 'big'}):
        raise ValueError('invalid rune modes')
    color = meta.get('color')
    if color:
        mode = color.get('mode')
        if mode not in {'team', 'fixed', 'source_material'}:
            raise ValueError('invalid color mode')
        if mode == 'team' and not color.get('owner_ref'):
            raise ValueError('team color requires owner_ref')
        if mode == 'fixed':
            rgb = finite_vector(color.get('fixed_srgb'), 3, 'sRGB')
            if (rgb < 0).any() or (rgb > 1).any():
                raise ValueError('sRGB outside [0,1]')
    if 'collision' in meta and not isinstance(meta['collision'], bool):
        raise ValueError('collision must be boolean')
    if meta.get('collision') is False and 'decoration' not in roles:
        raise ValueError('only explicitly identified decoration may disable collision')
    if meta.get('layer', 'geometry') not in LAYERS:
        raise ValueError('invalid visual layer')


def resolve(document, selector):
    candidates = [i for i, _, _ in scene_nodes(document)
                  if document['nodes'][i].get('name') == selector['name']]
    if 'occurrence' in selector:
        occurrence = selector['occurrence']
        if not isinstance(occurrence, int) or occurrence < 0 or occurrence >= len(candidates):
            raise ValueError(f'bad occurrence selector: {selector}')
        return candidates[occurrence]
    if len(candidates) != 1:
        raise ValueError(f'selector must match exactly one node: {selector}, matches={len(candidates)}')
    return candidates[0]


def transform_asset(document, spec, source_hash, collision=False):
    """Return an annotated copy plus bindings. Binary mesh data is unchanged."""
    doc = copy.deepcopy(document)
    if doc.get('animations') or doc.get('skins'):
        raise ValueError('pre-existing animations/skins require a dedicated migration')
    original = list(scene_nodes(doc))
    world = {i: matrix for i, matrix, _ in original}
    parents = {i: parent for i, _, parent in original}
    nodes = doc['nodes']
    bindings, ids, bound = [], {}, set()
    specs = spec.get('nodes', [])
    selected = [(entry, resolve(doc, entry['select'])) for entry in specs]
    for entry, index in selected:
        meta = copy.deepcopy(entry['metadata'])
        validate_metadata(meta)
        if meta['id'] in ids or index in bound:
            raise ValueError('duplicate semantic id or node binding')
        ids[meta['id']] = index
        bound.add(index)
        meta['provenance'] = {'input_glb_sha256': source_hash, 'node_index': index,
                              'node_name': nodes[index].get('name'),
                              'evidence': entry.get('evidence', []),
                              'source_extras': copy.deepcopy(nodes[index].get('extras', {}))}
        if 'name' in entry:
            nodes[index]['name'] = entry['name']
        nodes[index].setdefault('extras', {})['rm'] = meta
        bindings.append({'id': meta['id'], 'node': index, 'metadata': meta})

    # Authored empty link frames let a sidecar describe a serial mechanism even
    # while a merged CAD mesh still needs a verified rigid-body partition.
    for entry in spec.get('frames', []):
        meta = copy.deepcopy(entry['metadata'])
        validate_metadata(meta)
        if meta['id'] in ids or not entry.get('evidence'):
            raise ValueError('frame needs a unique id and source evidence')
        if entry['parent'] not in ids:
            raise ValueError('frame parent must already be bound')
        parent = ids[entry['parent']]
        matrix = local_matrix({'translation': entry.get('translation_m', [0, 0, 0]),
                               'rotation': entry.get('rotation_xyzw', [0, 0, 0, 1])})
        index = len(nodes)
        meta['provenance'] = {'input_glb_sha256': source_hash,
                              'evidence': entry['evidence'], 'authored_frame': True}
        nodes.append({'name': entry.get('name', meta['id']),
                      'matrix': matrix.flatten(order='F').tolist(),
                      'extras': {'rm': meta}})
        nodes[parent].setdefault('children', []).append(index)
        ids[meta['id']] = index
        bound.add(index)
        parents[index] = parent
        world[index] = world[parent] @ matrix
        bindings.append({'id': meta['id'], 'node': index, 'metadata': meta})

    joints = []
    for joint in spec.get('joints', []):
        joint = copy.deepcopy(joint)
        jid = joint['id']
        if jid in ids or joint.get('type') not in {'continuous', 'revolute', 'prismatic'}:
            raise ValueError('duplicate joint id or invalid joint type')
        axis = finite_vector(joint['axis'], 3, 'joint axis')
        if not np.isclose(np.linalg.norm(axis), 1, atol=1e-6):
            raise ValueError('joint axis must be unit length')
        origin = finite_vector(joint['origin_m'], 3, 'joint origin')
        rotation = joint.get('rotation_xyzw', [0, 0, 0, 1])
        frame = local_matrix({'translation': origin.tolist(), 'rotation': rotation})
        limits = joint.get('limits')
        if limits is not None:
            lo, hi = finite_vector(limits, 2, 'joint limits')
            if lo > 0 or hi < 0 or lo > hi or joint['type'] == 'continuous':
                raise ValueError('limits must contain the zero rest coordinate; continuous joints have no limits')
        if 'preview_range' in joint:
            preview_lo, preview_hi = finite_vector(joint['preview_range'], 2, 'preview range')
            if preview_lo > preview_hi or (limits is not None and (preview_lo < lo or preview_hi > hi)):
                raise ValueError('invalid preview range')
        if not joint.get('evidence'):
            raise ValueError('joint needs source evidence')
        parent = ids[joint['parent']]
        children = [ids[c] for c in joint['children']]
        if not children or len(set(children)) != len(children):
            raise ValueError('joint needs unique moving children')
        for child in children:
            if parents.get(child) != parent:
                raise ValueError('moving children must be direct children of joint parent')
        frame_id, motion_id = len(nodes), len(nodes) + 1
        nodes.append({'name': jid + '/origin', 'translation': origin.tolist(),
                      'rotation': rotation, 'children': [motion_id]})
        nodes.append({'name': jid, 'translation': [0, 0, 0], 'rotation': [0, 0, 0, 1],
                      'children': children, 'extras': {'rm': {'id': jid, 'joint': joint}}})
        siblings = nodes[parent].get('children', [])
        first = min(siblings.index(i) for i in children)
        nodes[parent]['children'] = [i for i in siblings[:first] if i not in children] + [frame_id] + [i for i in siblings[first:] if i not in children]
        pivot_world = world[parent] @ frame
        for child in children:
            rest = np.linalg.inv(pivot_world) @ world[child]
            for key in ('translation', 'rotation', 'scale', 'matrix'):
                nodes[child].pop(key, None)
            nodes[child]['matrix'] = rest.flatten(order='F').tolist()
            parents[child] = motion_id
        joint['origin_node'], joint['motion_node'] = frame_id, motion_id
        joints.append(joint)
        ids[jid] = motion_id

    # Surface metadata belongs to mesh instances; clone mesh JSON before tagging
    # primitives so shared geometry can have different team/role bindings.
    surfaces = []
    excluded = []
    for entry in spec.get('surfaces', []):
        meta = copy.deepcopy(entry['metadata'])
        validate_metadata(meta)
        if meta['id'] in ids:
            raise ValueError('duplicate surface id')
        index = ids[entry['node_id']]
        node = nodes[index]
        if 'mesh' not in node:
            raise ValueError('surface must bind a mesh node')
        mesh = copy.deepcopy(doc['meshes'][node['mesh']])
        pi = entry['primitive']
        if not isinstance(pi, int) or pi < 0 or pi >= len(mesh['primitives']):
            raise ValueError('invalid primitive binding')
        primitive = mesh['primitives'][pi]
        if 'rm' in primitive.get('extras', {}):
            raise ValueError('primitive bound more than once')
        meta['provenance'] = {'input_glb_sha256': source_hash, 'node_index': index,
                              'primitive': pi, 'evidence': entry.get('evidence', [])}
        primitive.setdefault('extras', {})['rm'] = meta
        node['mesh'] = len(doc['meshes'])
        doc['meshes'].append(mesh)
        surfaces.append({'id': meta['id'], 'node': index, 'source_primitive': pi, 'metadata': meta})
        ids[meta['id']] = index
    for binding in bindings + surfaces:
        meta = binding['metadata']
        for key in ('module_id', 'target_frame'):
            if key in meta and meta[key] not in ids:
                raise ValueError(f'unresolved {key}: {meta[key]}')
    unknown = []
    for index, _, _ in original:
        node = nodes[index]
        if 'mesh' not in node:
            continue
        if index not in bound:
            stable_id = f'{spec["id"]}.unclassified.{index}'
            meta = {'id': stable_id, 'roles': ['unclassified'],
                    'color': {'mode': 'source_material'},
                    'provenance': {'input_glb_sha256': source_hash, 'node_index': index,
                                   'node_name': node.get('name')}}
            if stable_id in ids:
                raise ValueError('generated id conflicts with authored id')
            node.setdefault('extras', {})['rm'] = meta
            bindings.append({'id': stable_id, 'node': index, 'metadata': meta})
            unknown.append(stable_id)
        if collision:
            node_meta = node.get('extras', {}).get('rm', {})
            mesh = copy.deepcopy(doc['meshes'][node['mesh']])
            kept = []
            for pi, primitive in enumerate(mesh['primitives']):
                pm = primitive.get('extras', {}).get('rm', {})
                if node_meta.get('collision') is False or pm.get('collision') is False:
                    excluded.append({'node': index, 'primitive': pi, 'id': pm.get('id', node_meta.get('id'))})
                else:
                    kept.append(primitive)
            if kept:
                mesh['primitives'] = kept
                node['mesh'] = len(doc['meshes'])
                doc['meshes'].append(mesh)
            else:
                del node['mesh']
    # Bind retained surface indices after collision filtering, explicitly marking
    # excluded surfaces rather than leaving stale primitive references.
    for surface in surfaces:
        node = nodes[surface['node']]
        primitives = doc['meshes'][node['mesh']]['primitives'] if 'mesh' in node else []
        surface['primitive'] = next((i for i, p in enumerate(primitives)
                                    if p.get('extras', {}).get('rm', {}).get('id') == surface['id']), None)
    after = {i: matrix for i, matrix, _ in scene_nodes(doc)}
    for index, matrix, _ in original:
        if not np.allclose(after[index], matrix, atol=1e-10, rtol=0):
            raise ValueError(f'rest pose changed at node {index}')
    return doc, {'nodes': bindings, 'surfaces': surfaces, 'joints': joints,
                 'unclassified': unknown, 'collision_exclusions': excluded,
                 'pending': spec.get('pending', [])}


def apply_pose(document, joints, coordinates):
    """Evaluate authored joint coordinates on a copy; zero is the original CAD pose."""
    doc = copy.deepcopy(document)
    by_id = {j['id']: j for j in joints}
    if set(coordinates) - by_id.keys():
        raise ValueError('unknown joint coordinate')
    for jid, value in coordinates.items():
        joint = by_id[jid]
        if not np.isfinite(value):
            raise ValueError('non-finite joint coordinate')
        if joint.get('limits') is not None and not joint['limits'][0] <= value <= joint['limits'][1]:
            raise ValueError('joint coordinate outside limits')
        node = doc['nodes'][joint['motion_node']]
        axis = np.asarray(joint['axis'])
        if joint['type'] == 'prismatic':
            node['translation'] = (axis * value).tolist()
        else:
            node['rotation'] = [*(axis * np.sin(value / 2)).tolist(), float(np.cos(value / 2))]
    return doc


def annotate_package(root, rules, rules_hash, geometry_source_root=None):
    """Mutate a new export directory; caller owns staging/atomic installation."""
    root = Path(root)
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if rules.get('schema_version') != 1:
        raise ValueError('unsupported semantics rules schema')
    if 'source_sha256' in rules and rules['source_sha256'] != manifest.get('source_sha256'):
        raise ValueError('semantic rules source mismatch')
    sidecar = {'schema_version': 1, 'units': {'length': 'metres', 'angle': 'radians'},
               'frame': 'GLB selected scene coordinates before external instance placement',
               'quaternion_order': 'xyzw', 'rules_sha256': rules_hash,
               'layers': LAYERS, 'layer_policy': 'Visibility categories only; collision exclusion requires explicit collision=false on decoration.',
               'assets': {}}
    for name, spec in rules['assets'].items():
        entry = manifest['assets'][name]
        record = {'id': spec['id'], 'files': {}}
        for kind in ('visual', 'collision'):
            if kind not in entry:
                continue
            path = safe_path(root, entry[kind])
            original_hash = digest(path)
            if original_hash != entry[kind + '_sha256']:
                raise ValueError(f'checksum mismatch: {path}')
            expected = spec.get('input_sha256', {}).get(kind)
            if expected is None or original_hash != expected:
                raise ValueError(f'{name}/{kind}: rules must pin the exact input GLB checksum')
            document, binary = read_glb(path)
            from semantic_geometry import split_geometry
            document, binary, resolved_spec = split_geometry(document, binary, spec)
            from semantic_reconstruction import add_reconstruction
            document, binary, resolved_spec = add_reconstruction(document, binary, resolved_spec, geometry_source_root or root)
            document, bindings = transform_asset(document, resolved_spec, original_hash, kind == 'collision')
            write_glb(path, document, binary)
            entry[kind + '_sha256'] = digest(path)
            entry[kind + '_bytes'] = path.stat().st_size
            record['files'][kind] = {'file': entry[kind], 'sha256': entry[kind + '_sha256'], **bindings}
            count = sum(document['accessors'][p['indices']]['count'] // 3 if 'indices' in p
                        else document['accessors'][p['attributes']['POSITION']]['count'] // 3
                        for i, _, _ in scene_nodes(document) if 'mesh' in document['nodes'][i]
                        for p in document['meshes'][document['nodes'][i]['mesh']]['primitives'])
            entry['triangles' if kind == 'visual' else 'collision_triangles'] = count
        entry['semantics'] = {'file': 'articulation.json', 'asset': name}
        sidecar['assets'][name] = record
    sidecar_path = root / 'articulation.json'
    sidecar_path.write_text(json.dumps(sidecar, indent=2, allow_nan=False) + '\n')
    manifest['articulation'] = {'file': sidecar_path.name, 'sha256': digest(sidecar_path), 'schema_version': 1}
    manifest['collision_contract'] = manifest.get('collision_contract', '') + (
        ' Explicitly tagged decoration is excluded for semantic assets; see articulation.json. '
        'Unclassified geometry retains collision.')
    if 'full-map' in manifest['assets']:
        manifest['assets']['full-map']['semantics_status'] = 'static source snapshot; use component assets for joints and collision layers'
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
    return sidecar


def catalog(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    assets = {}
    for name, entry in manifest['assets'].items():
        doc, _ = read_glb(safe_path(root, entry['visual']))
        assets[name] = {'input_sha256': {k: entry[k + '_sha256'] for k in ('visual', 'collision') if k in entry},
                        'nodes': [{'index': i, 'name': doc['nodes'][i].get('name'), 'parent': parent,
                                   'matrix_to_asset': matrix.tolist(),
                                   'primitives': len(doc['meshes'][doc['nodes'][i]['mesh']]['primitives'])
                                   if 'mesh' in doc['nodes'][i] else 0}
                                  for i, matrix, parent in scene_nodes(doc)]}
    return {'schema_version': 1, 'source_sha256': manifest.get('source_sha256'), 'assets': assets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--rules', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--geometry-source-root', type=Path, help='Read-only root containing checksum-pinned reconstruction donor GLBs')
    args = parser.parse_args()
    if args.catalog:
        args.catalog.write_text(json.dumps(catalog(args.package), indent=2) + '\n')
        return
    if args.rules is None or args.out is None:
        parser.error('--rules and --out are required for export')
    if args.out.exists() or args.out.resolve().is_relative_to(args.package.resolve()):
        parser.error('output must be a new directory outside the input package')
    rules = json.loads(args.rules.read_text())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent, prefix='.semantics-') as staging:
        stage = Path(staging) / 'package'
        shutil.copytree(args.package, stage)
        result = annotate_package(stage, rules, digest(args.rules), args.geometry_source_root or args.package)
        stage.rename(args.out)
    print(f'Wrote {args.out}: {len(result["assets"])} semantic assets')


if __name__ == '__main__':
    main()
