# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Collision simplification must retain openings and independent boundaries."""
import unittest
import numpy as np
from cad_collision_proxy import collision_proxy
from mesh_quality import distances


def subdivide(p, t, levels=2):
    for _ in range(levels):
        xyz = p[t]; a, b, c = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        xyz = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
        p, inv = np.unique(xyz.reshape(-1, 3), axis=0, return_inverse=True); t = inv.reshape(-1, 3)
    return p, t


def cube():
    p = np.array([[x, y, z] for x in [0., 20] for y in [0., 30] for z in [0., 40]])
    t = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    return p, t


class CollisionProxyTests(unittest.TestCase):
    def test_closed_rotated_box_becomes_a_primitive(self):
        p, t = subdivide(*cube()); original = p.copy(); q, f, proof = collision_proxy(p, t, sampled_limit_mm=1)
        self.assertEqual(proof['operation'], 'box'); self.assertEqual(len(f), 12)
        np.testing.assert_array_equal(p, original)
        # A rigid rotation preserves the fit and its coordinate-frame metadata.
        angle = .37; r = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
        p = p @ r.T + [500, 100, -20]; q, f, proof = collision_proxy(p, t, sampled_limit_mm=1)
        self.assertEqual(proof['operation'], 'box'); self.assertLess(proof['box_trials'][-1]['maximum_sampled_deviation_mm'], 1e-6)

    def test_open_box_is_not_closed_by_a_proxy(self):
        p, t = cube(); p, t = subdivide(p, t[2:])
        q, f, proof = collision_proxy(p, t, sampled_limit_mm=3)
        self.assertNotEqual(proof['operation'], 'box')
        # Missing x=0 face remains open; closest source is ten millimetres away.
        self.assertGreater(distances(np.array([[0., 15, 20]]), q, f)[0], 9.99)
        edges = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
        keys, counts = np.unique(edges, axis=0, return_counts=True)
        have = set(map(tuple, q)); self.assertTrue(all(tuple(v) in have for v in p[np.unique(keys[counts == 1])]))

    def test_closed_hollow_frame_keeps_its_window(self):
        loop = np.array([[0., 0], [40, 0], [40, 40], [0, 40], [10, 10], [30, 10], [30, 30], [10, 30]])
        p = np.concatenate([np.column_stack([loop, np.full(8, z)]) for z in [0., 2]])
        quads = []
        for i in range(4):
            j = (i + 1) % 4
            quads.extend([[i, j, j + 8, i + 8], [i + 4, i + 12, j + 12, j + 4], [i, i + 4, j + 4, j], [i + 8, j + 8, j + 12, i + 12]])
        t = np.array([tri for a, b, c, d in quads for tri in [[a, b, c], [a, c, d]]]); p, t = subdivide(p, t, 1)
        q, f, proof = collision_proxy(p, t, sampled_limit_mm=3)
        self.assertNotEqual(proof['operation'], 'box')
        self.assertGreater(distances(np.array([[20., 20, 1]]), q, f)[0], 9.99)

    def test_invalid_policy(self):
        p, t = cube()
        with self.assertRaises(ValueError): collision_proxy(p, t, sampled_limit_mm=-1)
