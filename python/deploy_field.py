# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compose and install rm-simulator assets without OCCT or re-tessellation.

Keeps the field package's animation-ready rune and outpost; takes the base
and tech core, the static elements and the V1.2.0 outpost footings from the
elements package, collision proxies included. Uses only the Python standard
library. An existing destination requires --replace and is retained as a
dated backup.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import time

STATIC = ('centre-platform', 'dart-station', 'resource-zone')
EQUIPMENT = ('base', 'tech-core')


def digest(path):
    with path.open('rb') as stream:
        value = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
        return value.hexdigest()


def read_manifest(root):
    value = json.loads((root / 'manifest.json').read_text())
    if value['schema_version'] != 1 or value['units'] != 'metres':
        raise ValueError(f'unsupported manifest: {root}')
    return value


def asset_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'asset path escapes package: {name}')
    return path


def copy_asset(source, destination, entry):
    for kind in ('visual', 'collision'):
        if kind not in entry:
            continue
        src = asset_path(source, entry[kind])
        if digest(src) != entry[kind + '_sha256']:
            raise ValueError(f'checksum mismatch: {src}')
        dst = asset_path(destination, entry[kind])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def extract_footing(source, destination):
    """Keep only the footing mesh; compact its accessors and binary payload.

    export_elements bakes the local arena axes into vertices. Its root and
    product nodes have no transforms. Refuse a changed export convention.
    """
    data = source.read_bytes()
    magic, version, length = struct.unpack_from('<III', data)
    size, kind = struct.unpack_from('<II', data, 12)
    if (magic, version, length, kind) != (0x46546C67, 2, len(data), 0x4E4F534A):
        raise ValueError('unsupported GLB')
    document = json.loads(data[20:20 + size])
    offset = 20 + size
    binary_size, binary_kind = struct.unpack_from('<II', data, offset)
    if binary_kind != 0x004E4942:
        raise ValueError('missing GLB binary buffer')
    binary = data[offset + 8:offset + 8 + binary_size]
    selected = [n for n in document['nodes'] if n.get('name', '').endswith('_0008_1')]
    if len(selected) != 1 or any(any(k in n for k in ('matrix', 'translation', 'rotation', 'scale')) for n in document['nodes']):
        raise ValueError('unexpected outpost footing nodes or transforms')
    mesh = copy.deepcopy(document['meshes'][selected[0]['mesh']])
    output = {'asset': document['asset'], 'scene': 0, 'scenes': [{'nodes': [0]}],
              'nodes': [{'name': selected[0]['name'], 'mesh': 0}], 'meshes': [mesh],
              'materials': document.get('materials', []), 'accessors': [], 'bufferViews': []}
    payload = bytearray()
    accessors, views = {}, {}

    def accessor(old):
        if old in accessors:
            return accessors[old]
        item = copy.deepcopy(document['accessors'][old])
        if 'sparse' in item:
            raise ValueError('sparse accessors unsupported')
        view_id = item['bufferView']
        if view_id not in views:
            view = copy.deepcopy(document['bufferViews'][view_id])
            if view['buffer'] != 0:
                raise ValueError('external buffers unsupported')
            start = view.get('byteOffset', 0)
            payload.extend(b'\0' * (-len(payload) % 4))
            view['byteOffset'] = len(payload)
            payload.extend(binary[start:start + view['byteLength']])
            views[view_id] = len(output['bufferViews'])
            output['bufferViews'].append(view)
        item['bufferView'] = views[view_id]
        accessors[old] = len(output['accessors'])
        output['accessors'].append(item)
        return accessors[old]

    for primitive in mesh['primitives']:
        primitive['indices'] = accessor(primitive['indices'])
        primitive['attributes'] = {k: accessor(v) for k, v in primitive['attributes'].items()}
    output['buffers'] = [{'byteLength': len(payload)}]
    text = json.dumps(output, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    payload.extend(b'\0' * (-len(payload) % 4))
    result = struct.pack('<III', 0x46546C67, 2, 28 + len(text) + len(payload))
    result += struct.pack('<II', len(text), 0x4E4F534A) + text
    result += struct.pack('<II', len(payload), 0x004E4942) + payload
    destination.write_bytes(result)


def visual_collision(root, entry):
    """Retain source-tessellated colliders; replace untrusted legacy proxies."""
    if entry.get("collision_method") == "source-tessellation-v1":
        if not entry.get("collision") or not entry.get("collision_sha256"):
            raise ValueError("source-tessellation-v1 requires a checksummed collision file")
        return
    visual = asset_path(root, entry['visual'])
    filename = visual.stem + '-collision.glb'
    destination = root / filename
    shutil.copy2(visual, destination)
    entry.update(collision=filename, collision_sha256=digest(destination),
                 collision_bytes=destination.stat().st_size,
                 collision_method='visual triangles; node hierarchy preserved')
    if 'triangles' in entry:
        entry['collision_triangles'] = entry['triangles']
    # Old extraction reports describe hulls/prisms, not the replacement mesh.
    entry.pop('parts', None)


def compose(field, elements, output):
    manifest = read_manifest(field)
    extra = read_manifest(elements)
    validation = elements / 'validation.json'
    if validation.exists() and not json.loads(validation.read_text()).get('ok'):
        raise ValueError('element export validation failed; refusing deployment')
    for key in ('source_sha256', 'floor_top_source_z_m'):
        if manifest.get(key) != extra.get(key):
            raise ValueError(f'field and elements disagree on {key}')
    for name in ('floor', 'arena-static'):
        if manifest['assets'][name]['visual_sha256'] != extra['assets'][name]['visual_sha256']:
            raise ValueError(f'field and elements disagree on {name}')
    # Copy only the runtime assets, not full-map, STEP or preview files.
    for name in ('floor', 'arena-static', 'rune', 'outpost'):
        copy_asset(field, output, manifest['assets'][name])
    # The base and tech core come from the elements export: source solids
    # and sheet surfaces next to each visual, both in the same
    # Z-up local frame, placed on the arena. The field package's equipment
    # copies have an older tech-core placement 0.76 m inside the platform.
    equipment = {'schema_version': 1, 'units': 'metres', 'generator': extra.get('generator'),
                 'source_sha256': extra['source_sha256'],
                 'collision_solids': extra.get('collision_solids', False),
                 'collision_contract': extra.get('collision_contract'),
                 'export_policy': extra.get('export_policy'),
                 'status': 'visuals and collision proxies from the elements export; joints not assigned',
                 'assets': {}}
    (output / 'equipment').mkdir()
    for name in EQUIPMENT:
        entry = copy.deepcopy(extra['assets'][name])
        entry.pop('step', None)
        if 'collision' not in entry:
            raise ValueError(f'elements package has no collision proxy for {name}')
        copy_asset(elements, output / 'equipment', entry)
        equipment['assets'][name] = entry
    for entry in equipment['assets'].values():
        visual_collision(output / 'equipment', entry)
    (output / 'equipment/manifest.json').write_text(json.dumps(equipment, indent=2) + '\n')
    for name in STATIC:
        entry = copy.deepcopy(extra['assets'][name])
        entry.pop('step', None)
        copy_asset(elements, output, entry)
        manifest['assets'][name] = entry
    if 'outpost-footing' in extra['assets']:
        footing = copy.deepcopy(extra['assets']['outpost-footing'])
        footing.pop('step', None)
        copy_asset(elements, output, footing)
    else:
        footing = legacy_footing(elements, output, extra['assets']['outpost'])
    manifest['assets']['outpost-footing'] = footing
    manifest['static_assets'] = [*STATIC, 'outpost-footing']
    for name in ('floor', 'arena-static', 'rune', 'outpost', *manifest['static_assets']):
        visual_collision(output, manifest['assets'][name])
    manifest['collision_solids'] = False
    manifest['collision_contract'] = ('Source-tessellated colliders where collision_method is '
                                      'source-tessellation-v1; visual triangles otherwise. '
                                      'Sheets and markings retained; two-sided contacts required.')
    manifest['deployment'] = {'generator': 'rm-map-tools deploy_field.py',
                              'field_manifest_sha256': digest(field / 'manifest.json'),
                              'elements_manifest_sha256': digest(elements / 'manifest.json'),
                              'field_export_policy': manifest.get('export_policy'),
                              'elements_export_policy': extra.get('export_policy')}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output / 'deployment.json').write_text(json.dumps({'ok': True, **manifest['deployment'],
        'static_assets': manifest['static_assets']}, indent=2) + '\n')


def legacy_footing(elements, output, outpost):
    """Compatibility with the first elements export, whose origin used vertex boxes."""
    placements = copy.deepcopy(outpost['placements_in_source_arena_frame'])
    # The V1.2.0 outpost body is 3.607 degrees off its axis-aligned footing.
    # The reference footprint is centred on the outpost origin, and the two
    # footing occurrences are exact half-turns in the source STEP.
    for placement in placements:
        q = placement['rotation_xyzw']
        placement['rotation_xyzw'] = [0, 0, 1, 0] if abs(q[2]) > 0.9 else [0, 0, 0, 1]
        for key in ('matrix_local_to_arena', 'products_placed_differently', 'method', 'bbox_residual_m'):
            placement.pop(key, None)
    footing = {'placements_in_source_arena_frame': placements, 'source_products': [13267542],
               'source_asset': 'outpost', 'source_node': 'source_13267542_0008_1'}
    for kind in ('visual', 'collision'):
        src = asset_path(elements, outpost[kind])
        if digest(src) != outpost[kind + '_sha256']:
            raise ValueError(f'checksum mismatch: {src}')
        filename = 'outpost-footing' + ('-collision' if kind == 'collision' else '') + '.glb'
        extract_footing(src, output / filename)
        footing[kind] = filename
        footing[kind + '_sha256'] = digest(output / filename)
    return footing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    assets = Path.home() / 'dev/RM/assets'
    parser.add_argument('--field', type=Path, default=assets / 'rm2026-field')
    parser.add_argument('--elements', type=Path, default=assets / 'rm2026-field-elements')
    parser.add_argument('--out', type=Path, default=assets / 'rm2026-field')
    parser.add_argument('--replace', action='store_true', help='retain existing destination as a dated backup')
    args = parser.parse_args()
    destination = args.out.resolve()
    if destination.exists() and not args.replace:
        parser.error('destination exists; use --replace to retain it as a backup')
    if destination == args.elements.resolve():
        parser.error('destination must not replace the elements package')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.rm-field-', dir=destination.parent))
    backup = None
    try:
        compose(args.field.resolve(), args.elements.resolve(), stage)
        if destination.exists():
            backup = destination.with_name(destination.name + '.backup-' + str(time.time_ns()))
            destination.rename(backup)
        try:
            stage.rename(destination)
        except BaseException:
            if backup:
                backup.rename(destination)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(f'Installed {destination}')
    if backup:
        print(f'Previous package retained at {backup}')


if __name__ == '__main__':
    main()
