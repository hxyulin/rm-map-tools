# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Coverage repairs catch omitted surfaces without a camera or aggregate budget."""
import unittest
import numpy as np
from cad_surface_coverage import coverage_repair


class CoverageTests(unittest.TestCase):
    def square(self):
        return np.array([[0., 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]), np.array([[0, 1, 2], [0, 2, 3]])

    def test_missing_half_of_a_flat_panel_restores_the_whole_piece(self):
        p, t = self.square()
        keep, restore, report = coverage_repair(p, t, p, t[:1])
        self.assertFalse(keep.any()); self.assertTrue(restore.all())
        self.assertEqual(report['restored_pieces'], [0])

    def test_different_valid_diagonal_keeps_the_candidate(self):
        p, t = self.square(); other = np.array([[0, 1, 3], [1, 2, 3]])
        keep, restore, _ = coverage_repair(p, t, p, other)
        self.assertTrue(keep.all()); self.assertFalse(restore.any())

    def test_lost_disconnected_piece_does_not_restore_its_good_neighbor(self):
        p, t = self.square(); p = np.concatenate([p, p + [3, 0, 0]])
        source = np.concatenate([t, t + 4])
        keep, restore, _ = coverage_repair(p, source, p, t)
        self.assertTrue(keep.all()); np.testing.assert_equal(restore, [False, False, True, True])

    def test_removing_a_bridge_rechecks_newly_exposed_pieces(self):
        p = np.array([[0., 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0],
                      [.5, .5, 0], [1.5, .5, 0], [1.5, 1.5, 0], [.5, 1.5, 0],
                      [.8, .7, 0], [1.2, .7, 0], [1.2, 1.1, 0]])
        ring = np.array([[0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                         [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
        source = np.concatenate([ring, [[8, 9, 10]]])
        keep, restore, _ = coverage_repair(p, source, p, np.array([[0, 1, 2]]))
        self.assertFalse(keep.any()); self.assertTrue(restore.all())

    def test_unknown_vertices_and_invalid_policy_are_rejected(self):
        p, t = self.square()
        with self.assertRaises(ValueError): coverage_repair(p, t, p + .1, t)
        with self.assertRaises(ValueError): coverage_repair(p, t, p, t, distance_m=float('nan'))


if __name__ == '__main__': unittest.main()
