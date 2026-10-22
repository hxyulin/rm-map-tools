# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import unittest
import numpy as np
from cad_planar_panels import rebuild_panels


def grid(nx=4, ny=3, step=20):
    result = []
    for i in range(nx):
        for j in range(ny):
            a = np.array([i, j, 0.]) * step
            b = a + [step, 0, 0]
            c = a + [step, step, 0]
            d = a + [0, step, 0]
            result.extend([[a, b, c], [a, c, d]])
    return np.array(result)


class PlanarPanelTests(unittest.TestCase):
    def test_full_rectangle_rebuilt_with_two_triangles(self):
        source = grid()
        keep, patch, rows = rebuild_panels(source, source)
        self.assertEqual(len(keep), 0)
        self.assertEqual(len(patch), 2)
        self.assertEqual(rows[0]['holes'], 0)
        self.assertLess(rows[0]['triangulation_symmetric_difference_mm2'], 1e-6)

    def test_repairs_missing_corner_in_candidate(self):
        source = grid()
        keep, patch, rows = rebuild_panels(source, source[2:])
        self.assertEqual(len(keep), 0)
        self.assertEqual(len(patch), 2)
        self.assertAlmostEqual(rows[0]['source_area_mm2'], 80 * 60)

    def test_restores_completely_missing_broad_face(self):
        source = grid(1, 1, 200)
        keep, patch, rows = rebuild_panels(source, np.empty((0, 3, 3)))
        self.assertEqual(len(patch), 2)
        self.assertEqual(rows[0]['candidate_triangles'], 0)

    def test_tilted_candidate_is_replaced_not_overlaid(self):
        source = grid(1, 1, 200)
        candidate = source.copy()
        candidate[:, :, 2] = candidate[:, :, 0] / 200
        keep, patch, rows = rebuild_panels(source, candidate)
        self.assertEqual(len(keep), 0)
        self.assertEqual(len(patch), 2)
        self.assertTrue(np.all(patch[:, :, 2] == 0))

    def test_retains_holes_and_disconnected_panels(self):
        source = grid(5, 5)
        center = source.mean(1)
        source = source[~((center[:, 0] > 40) & (center[:, 0] < 60) &
                          (center[:, 1] > 40) & (center[:, 1] < 60))]
        source = np.concatenate([source, grid() + [200, 0, 0]])
        keep, patch, rows = rebuild_panels(source, source)
        self.assertEqual(len(keep), 0)
        self.assertEqual(rows[0]['holes'], 1)
        self.assertEqual(rows[0]['components'], 2)
        self.assertLess(len(patch), len(source))

    def test_opposite_winding_and_separated_planes_survive(self):
        g = grid()
        source = np.concatenate([g, g[:, ::-1], g + [0, 0, .5]])
        keep, patch, rows = rebuild_panels(source, source)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(patch), 6)
        self.assertEqual(len(keep), 0)
        normals = np.cross(patch[:, 1] - patch[:, 0], patch[:, 2] - patch[:, 0])
        self.assertEqual((normals[:, 2] < 0).sum(), 2)

    def test_unknown_extended_candidate_retains_group(self):
        source = grid()
        candidate = np.concatenate([source, [[[-10, -10, 0], [100, -10, 0], [100, 100, 0]]]])
        keep, patch, rows = rebuild_panels(source, candidate)
        self.assertEqual(len(keep), len(candidate))
        self.assertEqual(len(patch), 0)

    def test_invalid_data_or_policy_rejected(self):
        for source in (np.zeros((3, 3)), np.full((2, 3, 3), np.nan)):
            with self.assertRaises(ValueError): rebuild_panels(source, grid())
        with self.assertRaises(ValueError): rebuild_panels(grid(), grid(), plane_tolerance_mm=0)


if __name__ == '__main__':
    unittest.main()
