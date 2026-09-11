# SPDX-License-Identifier: MIT OR Apache-2.0
import unittest
import numpy as np
from decoration_backing import flat_backing


class FlatBackingTests(unittest.TestCase):
    def test_internal_marking_edges_disappear(self):
        points = np.array([[0,0,.4], [1,0,.4], [1,1,.4], [0,1,.4], [.5,.5,.4]])
        triangles = points[[[0,1,4], [1,2,4], [2,3,4], [3,0,4]]]
        result = flat_backing(triangles)
        self.assertEqual(len(result), 2)
        self.assertFalse(np.any(np.all(result == points[4], axis=2)))
        np.testing.assert_allclose(result[:, :, 2], .4)

    def test_real_deck_holes_are_retained(self):
        p = np.array([[0,0,.4], [3,0,.4], [3,3,.4], [0,3,.4],
                      [1,1,.4], [2,1,.4], [2,2,.4], [1,2,.4]])
        t = np.array([[0,1,5], [0,5,4], [1,2,6], [1,6,5],
                      [2,3,7], [2,7,6], [3,0,4], [3,4,7]])
        result = flat_backing(p[t])
        for tri in result:
            a, b, c = tri[:, :2]
            weights = np.linalg.solve(np.column_stack([b-a,c-a]), np.array([1.5,1.5])-a)
            self.assertFalse(np.all(weights >= 0) and weights.sum() <= 1)

    def test_duplicate_faces_rejected(self):
        tri = np.array([[[0.,0,.4], [1,0,.4], [0,1,.4]]])
        with self.assertRaises(ValueError):
            flat_backing(np.repeat(tri, 3, axis=0))


if __name__ == '__main__':
    unittest.main()
