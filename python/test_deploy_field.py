# SPDX-License-Identifier: MIT OR Apache-2.0
"""Standard-library tests: python3 -m unittest discover -s python -p 'test_deploy_field.py'."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from deploy_field import EQUIPMENT, STATIC, compose, digest, extract_footing


def glb():
    binary = struct.pack('<9f3I', 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
    document = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
        'nodes': [{'children': [1, 2]}, {'name': 'rotor', 'mesh': 0},
                  {'name': 'source_13267542_0008_1', 'mesh': 0}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1}]}],
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3'},
                      {'bufferView': 1, 'componentType': 5125, 'count': 3, 'type': 'SCALAR'}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36},
                        {'buffer': 0, 'byteOffset': 36, 'byteLength': 12}],
        'buffers': [{'byteLength': len(binary)}]}
    text = json.dumps(document).encode()
    text += b' ' * (-len(text) % 4)
    return (struct.pack('<III', 0x46546C67, 2, 28 + len(text) + len(binary))
            + struct.pack('<II', len(text), 0x4E4F534A) + text
            + struct.pack('<II', len(binary), 0x004E4942) + binary)


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.field, self.elements, self.out = [self.root / x for x in ('field', 'elements', 'out')]
        for path in (self.field, self.elements, self.out, self.field / 'equipment'):
            path.mkdir()
        for path in (self.field, self.elements, self.field / 'equipment'):
            (path / 'a.glb').write_bytes(glb() + (b'\0' * 4 if path == self.field / 'equipment' else b''))
            entry = {'visual': 'a.glb', 'collision': 'a.glb',
                'visual_sha256': digest(path / 'a.glb'), 'collision_sha256': digest(path / 'a.glb'),
                'placements_in_source_arena_frame': [
                    {'translation_m': [1, 2, 3], 'rotation_xyzw': [0, 0, 0, 1]},
                    {'translation_m': [-1, -2, 3], 'rotation_xyzw': [0, 0, 0.9995, -0.0315]}]}
            manifest = {'schema_version': 1, 'units': 'metres', 'source_sha256': 'source',
                'floor_top_source_z_m': -1.6, 'collision_solids': True, 'assets': {k: entry for k in
                    ('floor', 'arena-static', 'rune', 'outpost', *EQUIPMENT, *STATIC)}}
            (path / 'manifest.json').write_text(json.dumps(manifest))

    def test_composition_preserves_animated_assets_and_extracts_only_footing(self):
        compose(self.field, self.elements, self.out)
        manifest = json.loads((self.out / 'manifest.json').read_text())
        self.assertEqual(manifest['static_assets'], [*STATIC, 'outpost-footing'])
        self.assertEqual(digest(self.out / 'a.glb'), digest(self.field / 'a.glb'))
        footing = manifest['assets']['outpost-footing']
        self.assertEqual(footing['placements_in_source_arena_frame'][1]['rotation_xyzw'], [0, 0, 1, 0])
        data = (self.out / footing['visual']).read_bytes()
        document = json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])
        self.assertEqual(document['nodes'], [{'name': 'source_13267542_0008_1', 'mesh': 0}])
        self.assertEqual(len(document['meshes']), 1)
        self.assertEqual(digest(self.out / footing['visual']), footing['visual_sha256'])

    def test_equipment_comes_from_elements_with_collision_proxies(self):
        compose(self.field, self.elements, self.out)
        equipment = json.loads((self.out / 'equipment/manifest.json').read_text())
        self.assertEqual(sorted(equipment['assets']), sorted(EQUIPMENT))
        self.assertTrue(equipment['collision_solids'])
        for name in EQUIPMENT:
            entry = equipment['assets'][name]
            self.assertEqual(entry['collision_sha256'], digest(self.elements / 'a.glb'))
            self.assertEqual(digest(self.out / 'equipment' / entry['collision']), entry['collision_sha256'])
            self.assertEqual(len(entry['placements_in_source_arena_frame']), 2)
        self.assertNotEqual(digest(self.out / 'equipment/a.glb'), digest(self.field / 'equipment/a.glb'))

    def test_equipment_without_collision_is_rejected(self):
        path = self.elements / 'manifest.json'
        document = json.loads(path.read_text())
        document['assets']['base'] = {k: v for k, v in document['assets']['base'].items()
                                      if not k.startswith('collision')}
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, 'no collision proxy for base'):
            compose(self.field, self.elements, self.out)

    def test_source_tessellation_survives_deployment(self):
        path = self.elements / 'manifest.json'
        document = json.loads(path.read_text())
        # A distinct checksummed collider must not be overwritten by the visual.
        proxy = self.elements / 'source-collision.glb'
        proxy.write_bytes(glb() + b'fixture')
        for name in EQUIPMENT:
            document['assets'][name].update(
                collision='source-collision.glb', collision_sha256=digest(proxy),
                collision_method='source-tessellation-v1')
        path.write_text(json.dumps(document))
        compose(self.field, self.elements, self.out)
        equipment = json.loads((self.out / 'equipment/manifest.json').read_text())
        for entry in equipment['assets'].values():
            self.assertEqual(entry['collision_method'], 'source-tessellation-v1')
            self.assertEqual((self.out / 'equipment' / entry['collision']).read_bytes(), proxy.read_bytes())

    def test_corruption_is_rejected(self):
        (self.elements / 'a.glb').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            compose(self.field, self.elements, self.out)

    def test_mismatched_arena_is_rejected(self):
        path = self.elements / 'manifest.json'
        document = json.loads(path.read_text())
        document['floor_top_source_z_m'] = -1.5
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, 'disagree'):
            compose(self.field, self.elements, self.out)

    def test_bad_glb_is_rejected(self):
        (self.root / 'bad.glb').write_bytes(b'x' * 100)
        with self.assertRaises(ValueError):
            extract_footing(self.root / 'bad.glb', self.root / 'out.glb')


if __name__ == '__main__':
    unittest.main()
