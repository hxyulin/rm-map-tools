# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import unittest
import numpy as np

from export_semantics import apply_pose, transform_asset
from gltf_scene import mesh_instances
from semantic_geometry import split_geometry
from test_gltf_scene import fixture
from test_semantics import rules


class GeometryPartitionTests(unittest.TestCase):
    def test_fixed_primitive_retains_rest_pose_while_sibling_rotates(self):
        doc, binary = fixture()
        doc['meshes'][0]['primitives'].append(copy.deepcopy(doc['meshes'][0]['primitives'][0]))
        spec = rules()
        spec['surfaces'] = []
        spec['geometry_groups'] = [{'select': {'name': 'plate'}, 'parent': {'name': 'root'},
            'name': 'fixed_logo', 'parts': [{'primitive': 0}],
            'metadata': {'id': 'fixed_logo', 'roles': ['decoration']}, 'evidence': ['fixture']}]
        split, payload, spec = split_geometry(doc, binary, spec)
        result, meta = transform_asset(split, spec, 'hash')
        moved = apply_pose(result, meta['joints'], {'spin': np.pi / 2})
        fixed_id = next(i for i, n in enumerate(result['nodes']) if n['name'] == 'fixed_logo')
        before = {(i, p): x for i, p, x, _, _ in mesh_instances(result, payload)}
        after = {(i, p): x for i, p, x, _, _ in mesh_instances(moved, payload)}
        np.testing.assert_array_equal(before[fixed_id, 0], after[fixed_id, 0])
        self.assertFalse(np.allclose(before[1, 0], after[1, 0]))
        self.assertEqual(sum(len(t) for _, _, _, t, _ in mesh_instances(result, payload)), 4)
        np.testing.assert_allclose(before[fixed_id, 0], [[11, 2, 0], [12, 2, 0], [11, 3, 0]])

    def test_partition_bounds_ignore_unreferenced_vertex_storage(self):
        doc, binary = fixture()
        # A six-vertex buffer shared by two triangles that are split into nodes.
        points = np.array([[1, 0, 0], [2, 0, 0], [1, 1, 0],
                           [100, 0, 0], [101, 0, 0], [100, 1, 0]], dtype='<f4')
        binary = points.tobytes()
        doc['accessors'][0]['count'] = 6
        doc['bufferViews'][0]['byteLength'] = len(binary)
        doc['buffers'][0]['byteLength'] = len(binary)
        spec = {'geometry_groups': [{'select': {'name': 'plate'}, 'parent': {'name': 'root'},
            'name': 'detail', 'parts': [{'primitive': 0, 'triangle_ranges': [[1, 2]]}],
            'metadata': {'id': 'detail', 'roles': ['assembly']}, 'evidence': ['fixture']}]}
        result, payload, _ = split_geometry(doc, binary, spec)
        instances = {i: xyz for i, _, xyz, _, _ in mesh_instances(result, payload)}
        self.assertEqual(instances[1][:, 0].max(), 12)
        self.assertEqual(instances[3][:, 0].min(), 110)

    def test_triangle_partition_preserves_membership_and_rejects_overlap(self):
        doc, binary = fixture()
        doc['accessors'][0]['count'] = 6
        doc['bufferViews'][0]['byteLength'] *= 2
        doc['buffers'][0]['byteLength'] *= 2
        binary *= 2
        spec = {'geometry_groups': [{'select': {'name': 'plate'}, 'parent': {'name': 'root'},
            'name': 'detail', 'parts': [{'primitive': 0, 'triangle_ranges': [[1, 2]]}],
            'metadata': {'id': 'detail', 'roles': ['assembly']}, 'evidence': ['fixture']}]}
        result, payload, _ = split_geometry(doc, binary, spec)
        self.assertEqual(sum(len(t) for _, _, _, t, _ in mesh_instances(result, payload)), 4)
        other = copy.deepcopy(spec['geometry_groups'][0]);other['name'] = 'duplicate'
        spec['geometry_groups'].append(other)
        with self.assertRaisesRegex(ValueError, 'overlapping geometry'):
            split_geometry(doc, binary, spec)


if __name__ == '__main__':
    unittest.main()
