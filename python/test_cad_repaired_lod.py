# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Repair missing sheets and hard-edge normals without changing source values."""
import unittest
from unittest.mock import patch
import numpy as np
from cad_repaired_lod import repaired_indices, selective_indices, visual_selector
from cad_experimental_lod import align_source_corners
from test_cad_collision_proxy import cube, subdivide


class RepairedLodTests(unittest.TestCase):
    def test_missing_box_faces_are_recovered(self):
        p, t = cube(); p /= 1000
        before = p.copy()
        f, report = repaired_indices(p, t, maximum_distance_mm=.1, allowed_bad_area_fraction=0)
        self.assertGreaterEqual(len(f), 12)
        self.assertLessEqual(report['maximum_sampled_distance_mm'], .1)
        np.testing.assert_array_equal(p, before)

    def test_separate_pieces_cannot_hide_each_others_missing_faces(self):
        p, t = cube(); p /= 1000
        p = np.concatenate([p, p + [.2, 0, 0]])
        t = np.concatenate([t, t + len(p) // 2])
        f, report = repaired_indices(p, t, maximum_distance_mm=.1, allowed_bad_area_fraction=0)
        self.assertEqual(len(report['pieces']), 2)
        self.assertTrue((f < len(p) // 2).all(1).any())
        self.assertTrue((f >= len(p) // 2).all(1).any())

    def test_textured_topology_is_exact(self):
        p, t = subdivide(*cube())
        f, proof = visual_selector(p / 1000, t, {'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}}, {})
        np.testing.assert_array_equal(f, t)
        self.assertEqual(proof['policy'], 'retain-textured')

    def test_source_corner_normal_matches_face_side(self):
        front = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0]])
        p = np.concatenate([front, front]); normals = np.array([[0, 0, -1]] * 3 + [[0, 0, 1]] * 3)
        f = align_source_corners(p, normals, np.array([[0, 1, 2], [3, 5, 4]]))
        np.testing.assert_array_equal(p[f], p[[[0, 1, 2], [3, 5, 4]]])
        self.assertTrue((normals[f[0], 2] == 1).all())
        self.assertTrue((normals[f[1], 2] == -1).all())

    def test_unselected_piece_keeps_low_indices(self):
        p, t = cube(); p /= 1000
        low = t[:2]
        with patch('cad_repaired_lod.coarse_indices', return_value=low):
            f, proof = selective_indices(p, t, {}, {}, [])
        np.testing.assert_array_equal(f, low)

    def test_invalid_guard(self):
        p, t = cube()
        for value in [0, -1, float('nan')]:
            with self.assertRaises(ValueError): repaired_indices(p, t, maximum_distance_mm=value)
        with self.assertRaises(ValueError): repaired_indices(p, t, allowed_bad_area_fraction=1)

    def test_new_interior_hole_cannot_pass_loose_surface_policy(self):
        p, t = cube(); p, t = subdivide(p, t[:2]); p /= 1000
        centers = p[t].mean(1)
        hole = (centers[:, 1] > .01) & (centers[:, 1] < .02) & (centers[:, 2] > .01) & (centers[:, 2] < .03)
        broken = t[~hole]
        with patch('cad_repaired_lod.coarse_indices', return_value=broken):
            f, report = repaired_indices(p, t, maximum_distance_mm=100, allowed_bad_area_fraction=.99)
        self.assertNotEqual(report['pieces'][0]['method'], 'cluster')
        self.assertLessEqual(report['pieces'][0]['maximum_boundary_loop_anchor_distance_mm'], 1)

    def test_unknown_piece_rejected(self):
        p, t = cube()
        with self.assertRaises(ValueError): selective_indices(p / 1000, t, {}, {}, [99999])

    def test_gap_repair_restores_exact_source_piece(self):
        p, t = cube()
        f, report = selective_indices(p / 1000, t, {}, {}, [], exact_pieces=[0])
        np.testing.assert_array_equal(f, t)
        self.assertEqual(report['repairs'][0]['policy'], 'retain-source-interior-gap')

    def test_gap_patch_adds_only_named_source_triangles_and_deduplicates(self):
        p, t = cube()
        with patch('cad_repaired_lod.coarse_indices', return_value=t[:2]):
            f, report = selective_indices(p / 1000, t, {}, {}, [], source_patch_triangles=[0, 3])
        self.assertEqual(len(f), 3)
        np.testing.assert_array_equal(f, np.concatenate([t[:2], t[[3]]]))

    def test_gap_patch_keeps_opposite_winding_face(self):
        p, t = cube(); t = np.concatenate([t, t[[0]][:, ::-1]])
        with patch('cad_repaired_lod.coarse_indices', return_value=t[:1]):
            f, report = selective_indices(p / 1000, t, {}, {}, [], source_patch_triangles=[12])
        self.assertEqual(len(f), 2)
        np.testing.assert_array_equal(f, t[[0, 12]])


if __name__ == '__main__': unittest.main()
