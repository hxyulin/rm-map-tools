# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from extract_entities import digest, partition, run
from gltf_scene import mesh_instances, read_glb, write_glb
from test_gltf_scene import fixture


def entity():
    return {'id': 'unit-1', 'origin_m': [11, 2, 0], 'parts': [
        {'node': 'plate', 'primitive': 0, 'triangle_ranges': [[0, 1]]}]}


def faces(doc, binary):
    return np.concatenate([v[t].reshape(-1, 3) for _, _, v, t, _ in mesh_instances(doc, binary)])


class ExtractionTests(unittest.TestCase):
    def test_shared_mesh_nested_transform_and_material_are_preserved(self):
        doc, binary = fixture()
        original = copy.deepcopy(doc)
        remaining, unit = partition(doc, binary, [entity()])
        self.assertEqual(doc, original)
        np.testing.assert_allclose(faces(*remaining), [[11, 0, 1], [12, 0, 1], [11, 1, 1]])
        np.testing.assert_allclose(faces(*unit), [[0, 0, 0], [1, 0, 0], [0, 1, 0]])
        self.assertEqual(unit[0]['materials'], doc['materials'])
        self.assertNotIn('mesh', remaining[0]['nodes'][1])
        self.assertIn('mesh', remaining[0]['nodes'][2])

    def test_partial_partition_keeps_winding_and_unused_vertices_out(self):
        doc, binary = fixture()
        doc['accessors'][0]['count'] = 6
        doc['bufferViews'][0]['byteLength'] *= 2
        doc['buffers'][0]['byteLength'] *= 2
        binary += (np.array([[4, 0, 0], [5, 0, 0], [4, 1, 0]], dtype='<f4')).tobytes()
        remaining, unit = partition(doc, binary, [entity()])
        self.assertEqual(len(faces(*remaining)), 9)
        self.assertEqual(len(faces(*unit)), 3)
        self.assertLessEqual(faces(*unit).max(), 1)

    def test_overlapping_invalid_and_empty_selections_fail(self):
        doc, binary = fixture()
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            partition(doc, binary, [entity(), entity()])
        for ranges in ([[0, 2]], [[-1, 1]], [[1, 0]], []):
            e = entity(); e['parts'][0]['triangle_ranges'] = ranges
            with self.assertRaises(ValueError):
                partition(doc, binary, [e])

    def test_package_placements_checksums_and_input_immutability(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); package = root / 'input'; package.mkdir()
            for name in ('v', 'c'):
                write_glb(package / (name + '.glb'), *fixture())
            entry = {'visual': 'v.glb', 'collision': 'c.glb',
                     'visual_sha256': digest(package / 'v.glb'), 'collision_sha256': digest(package / 'c.glb'),
                     'collision_method': 'source-tessellation-v1',
                     'placements_in_source_arena_frame': [{'instance': 0, 'translation_m': [5, 6, 7],
                         'rotation_xyzw': [0, 0, 1, 0], 'matrix_local_to_arena': [[-1, 0, 0, 5], [0, -1, 0, 6], [0, 0, 1, 7], [0, 0, 0, 1]]}]}
            (package / 'manifest.json').write_text(json.dumps({'assets': {'zone': entry}, 'static_assets': ['zone']}))
            original = (package / 'manifest.json').read_bytes()
            e = entity(); e['visual'] = e.pop('parts'); e['collision'] = e['visual']
            rules = {'schema_version': 1, 'asset': 'zone', 'evidence': ['fixture'], 'entities': [e],
                     'inputs': {k: {'sha256': entry[k + '_sha256']} for k in ('visual', 'collision')}}
            run(package, rules, root / 'out')
            m = json.loads((root / 'out/manifest.json').read_text())
            p = m['assets']['unit-1']['placements_in_source_arena_frame'][0]
            np.testing.assert_allclose(p['translation_m'], [-6, 4, 7])
            self.assertEqual(p['entity_id'], 'zone-0-unit-1')
            self.assertEqual((package / 'manifest.json').read_bytes(), original)
            for k in ('visual', 'collision'):
                self.assertEqual(digest(root / 'out' / m['assets']['unit-1'][k]), m['assets']['unit-1'][k + '_sha256'])
            rules['inputs']['collision']['sha256'] = 'bad'
            with self.assertRaisesRegex(ValueError, 'checksum'):
                run(package, rules, root / 'bad')
            self.assertFalse((root / 'bad').exists())


if __name__ == '__main__':
    unittest.main()
