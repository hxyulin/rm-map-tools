# SPDX-License-Identifier: MIT OR Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest

from export_semantics import digest
from gltf_scene import write_glb
from test_gltf_scene import fixture
from test_semantics import rules
from update_reference_assets import build_reference, verify_package


class ReferenceAssetsTests(unittest.TestCase):
    def test_build_verifies_nested_package_and_keeps_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            field = root / 'source'
            paths = []
            for sub in [field, field / 'equipment']:
                sub.mkdir(parents=True, exist_ok=True)
                doc, binary = fixture()
                write_glb(sub / 'mesh.glb', doc, binary)
                write_glb(sub / 'collision.glb', doc, binary)
                entry = {'visual': 'mesh.glb', 'collision': 'collision.glb',
                         'visual_sha256': digest(sub / 'mesh.glb'), 'collision_sha256': digest(sub / 'mesh.glb')}
                (sub / 'manifest.json').write_text(json.dumps({'assets': {'example': entry}}))
                spec = rules()
                spec['input_sha256'] = {k: entry[k + '_sha256'] for k in ['visual', 'collision']}
                path = root / ('equipment-rules.json' if sub.name == 'equipment' else 'field-rules.json')
                path.write_text(json.dumps({'schema_version': 1, 'assets': {'example': spec}}))
                paths.append(path)
            before = {str(p.relative_to(field)): digest(p) for p in field.rglob('*') if p.is_file()}
            out = root / 'reference'
            index = root / 'index.json'
            build_reference(field, out, *paths, index)
            result = verify_package(out)
            self.assertEqual(result['reference_equipment']['sha256'], digest(out / 'equipment/manifest.json'))
            self.assertEqual(json.loads(index.read_text())['manifest_sha256'], digest(out / 'manifest.json'))
            self.assertEqual(before, {str(p.relative_to(field)): digest(p) for p in field.rglob('*') if p.is_file()})
            with self.assertRaisesRegex(ValueError, 'exists'):
                build_reference(field, out, *paths, index)
            build_reference(field, out, *paths, index, replace=True)
            self.assertEqual(len(list(root.glob('reference.backup-*'))), 1)

    def test_refuses_overlapping_source_and_destination(self):
        with self.assertRaisesRegex(ValueError, 'separate'):
            build_reference('/tmp/example', '/tmp/example/ref', '', '', '')


if __name__ == '__main__':
    unittest.main()
