# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from export_semantics import apply_pose, annotate_package, digest, transform_asset, validate_metadata
from gltf_scene import mesh_instances, read_glb_nodes, scene_nodes, write_glb


from test_gltf_scene import fixture


def rules():
    return {'id': 'example', 'nodes': [
        {'select': {'name': 'root'}, 'metadata': {'id': 'root', 'roles': ['assembly']}},
        {'select': {'name': 'plate'}, 'name': 'example/armor_0',
         'metadata': {'id': 'plate', 'roles': ['armor_module'],
                      'armor': {'family': 'robot', 'size_class': 'small'}}},
        {'select': {'name': 'text'}, 'metadata': {'id': 'text', 'roles': ['decoration'],
                                                'layer': 'markings', 'collision': False}}],
        'joints': [{'id': 'spin', 'type': 'continuous', 'parent': 'root', 'children': ['plate'],
                    'origin_m': [0, 2, 0], 'axis': [0, 0, 1], 'evidence': ['synthetic fixture']}],
        'surfaces': [{'node_id': 'plate', 'primitive': 0,
                      'metadata': {'id': 'led', 'module_id': 'plate', 'roles': ['led_surface'],
                                   'led': {'function': 'armor_bar', 'channel': 'plate.lights'},
                                   'color': {'mode': 'team', 'owner_ref': 'instance.team'}}}]}


class SemanticsTests(unittest.TestCase):
    def test_joint_rest_and_quarter_turn(self):
        doc, binary = fixture()
        result, metadata = transform_asset(doc, rules(), 'hash')
        np.testing.assert_allclose({i: p for i, _, p, _, _ in mesh_instances(result, binary)}[1],
                                   [[11, 2, 0], [12, 2, 0], [11, 3, 0]])
        moved = apply_pose(result, metadata['joints'], {'spin': np.pi / 2})
        np.testing.assert_allclose({i: p for i, _, p, _, _ in mesh_instances(moved, binary)}[1],
                                   [[10, 3, 0], [10, 4, 0], [9, 3, 0]], atol=1e-12)
        self.assertNotIn('extras', doc['nodes'][1])
        self.assertEqual(result['nodes'][1]['name'], 'example/armor_0')
        self.assertEqual(metadata['nodes'][1]['metadata']['provenance']['node_name'], 'plate')

    def test_slider_limits_and_fixed_sibling(self):
        doc, binary = fixture()
        spec = rules()
        spec['joints'][0].update(type='prismatic', axis=[0, 1, 0], limits=[-.28, .28])
        result, meta = transform_asset(doc, spec, 'hash')
        moved = apply_pose(result, meta['joints'], {'spin': .28})
        instances = {i: p for i, _, p, _, _ in mesh_instances(moved, binary)}
        np.testing.assert_allclose(instances[1], [[11, 2.28, 0], [12, 2.28, 0], [11, 3.28, 0]])
        np.testing.assert_allclose(instances[2], [[11, 0, 1], [12, 0, 1], [11, 1, 1]])
        with self.assertRaisesRegex(ValueError, 'outside limits'):
            apply_pose(result, meta['joints'], {'spin': .281})

    def test_decoration_visual_preserved_collision_removed_shared_mesh_safe(self):
        doc, binary = fixture()
        visual, _ = transform_asset(doc, rules(), 'hash')
        collision, meta = transform_asset(doc, rules(), 'hash', collision=True)
        self.assertEqual(len(list(mesh_instances(visual, binary))), 2)
        self.assertEqual(len(list(mesh_instances(collision, binary))), 1)
        self.assertEqual(meta['collision_exclusions'], [{'node': 2, 'primitive': 0, 'id': 'text'}])
        self.assertEqual(meta['surfaces'][0]['primitive'], 0)

    def test_surface_only_exclusion_and_reindexing(self):
        doc, binary = fixture()
        doc['meshes'][0]['primitives'].append(copy.deepcopy(doc['meshes'][0]['primitives'][0]))
        spec = rules()
        spec['surfaces'].insert(0, {'node_id': 'plate', 'primitive': 1,
            'metadata': {'id': 'label', 'roles': ['decoration'], 'collision': False}})
        result, meta = transform_asset(doc, spec, 'hash', True)
        self.assertEqual(len(list(mesh_instances(result, binary))), 1)
        self.assertIsNone(meta['surfaces'][0]['primitive'])
        self.assertEqual(meta['surfaces'][1]['primitive'], 0)

    def test_reject_ambiguous_binding_cycles_and_bad_metadata(self):
        doc, _ = fixture()
        bad = copy.deepcopy(doc)
        bad['nodes'][2]['name'] = 'plate'
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            transform_asset(bad, rules(), 'hash')
        bad = copy.deepcopy(doc)
        bad['nodes'][1]['children'] = [0]
        with self.assertRaises(ValueError):
            list(scene_nodes(bad))
        for meta in [
            {'id': 'bad', 'roles': ['armor_module'], 'collision': False},
            {'id': 'bad', 'roles': ['led_surface'], 'color': {'mode': 'team'}},
            {'id': 'bad', 'roles': ['led_surface'], 'color': {'mode': 'fixed', 'fixed_srgb': [2, 0, 0]}},
            {'id': 'bad', 'roles': ['armor_module'], 'armor': {'family': 'robot', 'size_class': 'big'}},
        ]:
            with self.assertRaises(ValueError):
                validate_metadata(meta)

    def test_package_checksums_and_input_pinning(self):
        doc, binary = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in ['visual', 'collision']:
                write_glb(root / (kind + '.glb'), doc, binary)
            entry = {kind: kind + '.glb' for kind in ['visual', 'collision']}
            entry.update({kind + '_sha256': digest(root / (kind + '.glb')) for kind in ['visual', 'collision']})
            manifest = {'assets': {'example': entry}}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            spec = rules()
            spec['input_sha256'] = {kind: entry[kind + '_sha256'] for kind in ['visual', 'collision']}
            sidecar = annotate_package(root, {'schema_version': 1, 'assets': {'example': spec}}, 'ruleshash')
            result = json.loads((root / 'manifest.json').read_text())
            self.assertEqual(result['articulation']['sha256'], digest(root / 'articulation.json'))
            self.assertEqual(result['assets']['example']['collision_triangles'], 1)
            self.assertEqual(sidecar['assets']['example']['files']['visual']['sha256'], digest(root / 'visual.glb'))
            with self.assertRaisesRegex(ValueError, 'pin the exact'):
                annotate_package(root, {'schema_version': 1, 'assets': {'example': spec}}, 'ruleshash')


if __name__ == '__main__':
    unittest.main()
