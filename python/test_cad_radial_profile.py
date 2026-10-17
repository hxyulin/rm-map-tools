# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check radial envelope controls, topology, outward winding and source samples."""
import unittest
import numpy as np
from cad_radial_profile import profile_mesh, select_profile_rows, radial_samples


class RadialProfileTests(unittest.TestCase):
    def test_cylinder_volume_normals_and_material_seams(self):
        for axis in [0, 1, 2]:
            angles = np.arange(48) * 2 * np.pi / 48
            p, t, m = profile_mesh([0, 10, 30], angles, np.full((3, 48), 5.), np.tile(np.arange(48) % 2, (2, 1)), axis=axis, cap_material_ids=[2, 3])
            edges = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
            self.assertTrue(np.all(np.unique(edges, axis=0, return_counts=True)[1] == 2))
            g = p[t]; volume = np.einsum('ij,ij->i', g[:, 0], np.cross(g[:, 1], g[:, 2])).sum() / 6
            self.assertGreater(volume, 0)
            self.assertLess(abs(volume - np.pi * 25 * 30), 7)
            radii, colors = radial_samples(p, t, m, heights_mm=[5, 20], angles_rad=angles + .01, axis=axis)
            self.assertLess(abs(radii - 5).max(), .011)
            self.assertTrue(set(np.unique(colors)) <= {0, 1})
            with self.assertRaises(ValueError): radial_samples(p, t, m, heights_mm=[50], angles_rad=[0], axis=axis)

    def test_profile_chords_and_paint_breaks(self):
        h = np.arange(11, dtype=float); r = np.ones((11, 4)); r[5] = 2
        m = np.zeros_like(r, dtype=int); m[8:] = 1
        selected = select_profile_rows(h, r, m, tolerance_mm=.05)
        self.assertTrue({0, 4, 5, 6, 7, 8, 10} <= set(selected))
        selected = select_profile_rows(h, np.ones_like(r), np.zeros_like(m))
        self.assertEqual(selected.tolist(), [0, 10])
        with self.assertRaises(ValueError): select_profile_rows(h[::-1], r, m)
        with self.assertRaises(ValueError): profile_mesh([0, 1], [0, 1, 2], np.zeros((2, 3)), np.zeros((1, 3), int))

    def test_clipping_preserves_surface_paint_and_winding(self):
        from cad_radial_profile import clip_below
        p = np.array([[0., 0, 0], [2, 0, 0], [0, 2, 0], [0, -2, 0], [2, -2, 0], [0, -1, 0]])
        t = np.array([[0, 1, 2], [3, 4, 5]])
        q, f, m, owners = clip_below(p, t, np.array([5, 7]), axis=1, height_mm=1)
        self.assertEqual(len(f), 3); self.assertTrue(np.all(q[:, 1] <= 1))
        self.assertEqual(m.tolist(), [5, 5, 7]); self.assertEqual(owners.tolist(), [0, 0, 1])
        np.testing.assert_array_equal(q[f[-1]], p[t[-1]])
        g = q[f]; self.assertTrue(np.all(np.cross(g[:, 1] - g[:, 0], g[:, 2] - g[:, 0])[:, 2] > 0))
        self.assertTrue(np.all(g[:, :, 2] == 0))
