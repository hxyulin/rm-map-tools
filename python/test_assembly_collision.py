# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-local collision envelopes preserve the source and planar leaves."""
import unittest
import numpy as np
from assembly_collision import hull_or_mesh, link_local_points, C


class AssemblyCollisionTests(unittest.TestCase):
    def test_planar_leaf_keeps_triangle_topology_instead_of_failing_or_thickening(self):
        points = np.array([[0., 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 0]])
        triangles = np.array([[4, 1, 2], [0, 2, 3]])
        result = hull_or_mesh(points, triangles)
        self.assertEqual(result['kind'], 'mesh')
        np.testing.assert_array_equal(np.array(result['points_m'])[result['triangles']], points[triangles])
        np.testing.assert_array_equal(points[-1], points[0])

    def test_convex_leaf_bounds_every_source_vertex(self):
        from scipy.spatial import ConvexHull
        points = np.array([[x, y, z] for x in [-1., 1.] for y in [-1., 1.] for z in [-1., 1.]] + [[0., 0., 0.]])
        result = hull_or_mesh(points, np.array([[0, 1, 2]]))
        hull = ConvexHull(result['points_m'])
        self.assertEqual(len(result['points_m']), 8)
        self.assertLessEqual(np.max(points @ hull.equations[:, :3].T + hull.equations[:, 3]), 1e-12)

    def test_rotated_translated_native_link_roundtrips_to_flu(self):
        frame = np.eye(4)
        frame[:3, :3] = [[0., -1, 0], [1, 0, 0], [0, 0, 1]]
        frame[:3, 3] = [.3, -.4, .5]
        local = np.array([[.1, .2, .3], [-.2, .4, -.1]])
        source = (local @ C) @ frame[:3, :3].T + frame[:3, 3]
        before = source.copy()
        np.testing.assert_allclose(link_local_points(source, frame), local, atol=1e-12)
        np.testing.assert_array_equal(source, before)


if __name__ == '__main__':
    unittest.main()
