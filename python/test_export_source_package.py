"""Source assembly selection must preserve occurrence ownership and axes."""
from types import SimpleNamespace
import unittest

import numpy as np

from export_source_package import branches, source_rotation


class SourcePackageTests(unittest.TestCase):
    def test_duplicate_names_and_nested_shared_products_use_root_occurrences(self):
        move = np.eye(4)
        move[0, 3] = 500
        model = SimpleNamespace(roots=[0], children={0: [(10, 1), (11, 2), (12, 3), (13, 3)],
                                                     1: [(14, 3)]}, pname=lambda row: 'duplicate')
        ix = SimpleNamespace(ids=np.arange(100, 120), args=lambda row: b"'id','relationship','label',#1,#2,$")
        pkg = SimpleNamespace(m=model, ix=ix, bodies=lambda row: [], nauo_T={13: move})
        result = branches(pkg, {'product_names': {'101': 'red-road', '102': 'blue-road', '103': 'fan'}})
        self.assertEqual([v['name'] for v in result.values()], ['red-road', 'blue-road', 'fan'])
        self.assertEqual(result[3]['occurrences'], [112, 113])
        self.assertEqual(len(result[3]['matrices']), 2)
        np.testing.assert_array_equal(result[3]['matrices'][1], move)

    def test_y_up_conversion_is_proper_rotation_and_keeps_dimensions(self):
        matrix = source_rotation('y')
        np.testing.assert_array_equal(matrix[:3, :3] @ [0, 1, 0], [0, 0, 1])
        np.testing.assert_array_equal(matrix[:3, :3] @ [0, 0, 1], [0, -1, 0])
        self.assertEqual(np.linalg.det(matrix[:3, :3]), 1)
        np.testing.assert_array_equal(matrix.T @ matrix, np.eye(4))
        negative = source_rotation('-y')
        np.testing.assert_array_equal(negative[:3, :3] @ [0, -1, 0], [0, 0, 1])
        self.assertEqual(np.linalg.det(negative[:3, :3]), 1)
        with self.assertRaises(ValueError):
            source_rotation('x')


if __name__ == '__main__':
    unittest.main()
