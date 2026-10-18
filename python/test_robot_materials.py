# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Appearance changes preserve source paint, shared geometry and shell faces."""
import copy
import unittest

import numpy as np

from gltf_scene import mesh_instances
from robot_materials import apply_materials, classify, linear, verify_materials


class RobotMaterialTests(unittest.TestCase):
    def fixture(self, name='注塑滚子'):
        vertices = np.array([[0, 0, 0], [.018, 0, 0], [0, .018, 0], [0, 0, .04]], dtype='<f4')
        indices = np.array([0, 1, 2, 0, 3, 1, 0, 2, 3, 1, 3, 2], dtype='<u4')
        binary = vertices.tobytes() + indices.tobytes()
        document = {'scene': 0, 'scenes': [{'nodes': [0, 1]}],
            'nodes': [{'mesh': 0, 'extras': {'source_occurrence_paths': ['1']}},
                      {'mesh': 0, 'translation': [1, 2, 3], 'extras': {'source_occurrence_paths': ['2']}}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1, 'material': 0}]}],
            'materials': [{'extras': {'step_colour_origin': 'fallback', 'step_colour_srgb': None},
                           'pbrMetallicRoughness': {'baseColorFactor': [.5, .5, .5, 1]}}],
            'buffers': [{'byteLength': len(binary)}],
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': vertices.nbytes},
                            {'buffer': 0, 'byteOffset': vertices.nbytes, 'byteLength': indices.nbytes}],
            'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 4, 'type': 'VEC3'},
                          {'bufferView': 1, 'componentType': 5125, 'count': 12, 'type': 'SCALAR'}]}
        return document, binary, [{'path': '1', 'name': name}, {'path': '2', 'name': '铝轮毂'}]

    def test_shared_mesh_gets_distinct_materials_without_source_mutation(self):
        d, b, rows = self.fixture(); original = copy.deepcopy(d)
        original = copy.deepcopy(d)
        before = list(mesh_instances(d, b))
        result, report = apply_materials(d, b, rows)
        self.assertEqual(result, b)
        self.assertEqual(d['materials'][0], original['materials'][0])
        self.assertEqual(d['meshes'][0], original['meshes'][0])
        self.assertNotEqual(d['nodes'][0]['mesh'], d['nodes'][1]['mesh'])
        for a, z in zip(before, mesh_instances(d, result)):
            np.testing.assert_array_equal(a[2], z[2]); np.testing.assert_array_equal(a[3], z[3])
        self.assertEqual(report['primitive_counts'], {'rubber': 1, 'aluminum': 1})

    def test_source_paint_wins_over_name(self):
        d, b, rows = self.fixture()
        d['materials'][0]['extras'] = {'step_colour_origin': 'source', 'step_colour_srgb': [1, 0, 0]}
        original = copy.deepcopy(d)
        _, report = apply_materials(d, b, rows)
        self.assertEqual(d, original)
        self.assertEqual(report['primitive_counts'], {'source-painted': 2})

    def test_scoped_rules_do_not_color_clamps_or_whole_wheels_as_rubber(self):
        self.assertEqual(classify('碳管30管夹_CPY', [10, 30, 40])[0], 'aluminum')
        self.assertEqual(classify('底盘30碳管', [30, 30, 400])[0], 'carbon')
        self.assertEqual(classify('左旋麦轮', [22, 143, 143])[0], 'aluminum')
        self.assertEqual(classify('左旋麦轮', [18, 18, 38])[0], 'rubber')
        self.assertEqual(classify('装甲板支架', [14, 18, 59])[0], 'unknown-neutral')
        self.assertEqual(classify('小装甲板模块', [14, 18, 59])[0], 'team-diffuser')
        self.assertAlmostEqual(linear(.5), .21404114)

    def test_shell_split_retains_all_triangles_and_original_buffer(self):
        d, b, rows = self.fixture('HEXROLL-Left')
        # One roller-sized box shell and a disconnected large triangle.
        p = np.array([[x, y, z] for x in (0, .018) for y in (0, .019) for z in (0, .04)]
                     + [[1, 0, 0], [1, .08, 0], [1, 0, .08]], dtype='<f4')
        t = np.array([0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5,
                      0, 4, 5, 0, 5, 1, 2, 3, 7, 2, 7, 6,
                      0, 2, 6, 0, 6, 4, 1, 5, 7, 1, 7, 3, 8, 9, 10], dtype='<u4')
        b = p.tobytes() + t.tobytes()
        d['bufferViews'][0]['byteLength'] = p.nbytes
        d['bufferViews'][1].update(byteOffset=p.nbytes, byteLength=t.nbytes)
        d['accessors'][0]['count'] = len(p);d['accessors'][1]['count'] = len(t)
        d['buffers'][0]['byteLength'] = len(b)
        original = copy.deepcopy(d)
        before = list(mesh_instances(d, b))
        result, report = apply_materials(d, b, rows)
        self.assertEqual(result[:len(b)], b)
        after = list(mesh_instances(d, result))
        for index in (0, 1):
            expected = [tuple(x) for n, pi, p, t, m in before if n == index for x in p[t].reshape(-1, 9)]
            actual = [tuple(x) for n, pi, p, t, m in after if n == index for x in p[t].reshape(-1, 9)]
            self.assertEqual(sorted(expected), sorted(actual))
        self.assertIn('rubber', report['primitive_counts'])
        self.assertEqual(len(d['meshes'][d['nodes'][0]['mesh']]['primitives']), 2)
        self.assertTrue(verify_materials(original, b, d, result)['exact_triangle_multiplicity_preserved'])
        broken = copy.deepcopy(d)
        broken['meshes'][broken['nodes'][0]['mesh']]['primitives'].pop()
        with self.assertRaises(AssertionError):
            verify_materials(original, b, broken, result)


if __name__ == '__main__':
    unittest.main()
