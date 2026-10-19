# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-section and jaw clearance regressions, without CAD files or OCCT."""
import math
import unittest
import numpy as np
from gripper_fit import section_radius, pad_radius, fit_angle


class GripperFitTests(unittest.TestCase):
    def test_section_crosses_long_rods_without_vertices_at_the_grip_height(self):
        triangles = np.array([[[.03, -.01, -.05], [.03, .01, -.05], [.03, .01, .05]],
                              [[.03, -.01, -.05], [.03, .01, .05], [.03, -.01, .05]]])
        self.assertAlmostEqual(section_radius(triangles, [0., .01]), math.hypot(.03, .01))
        with self.assertRaises(ValueError):
            section_radius(triangles, [1.])
    def test_pad_uses_edge_distance_not_just_vertices(self):
        pad = np.array([[[-.01, .03, 0.], [.01, .03, 0.], [.01, .04, 0.]]])
        self.assertAlmostEqual(pad_radius(pad, np.zeros(3), 0.), .03)
    def test_stop_fits_known_sweep_and_rejects_an_oversize_unit(self):
        p = np.array([.02, .03, 0.]); pivot = np.array([-.05, 0., 0.])
        pad = np.array([[p, p, p]])
        x, y = p[:2] - pivot[:2]
        radius = math.hypot(pivot[0] + x * math.cos(.4) - y * math.sin(.4),
                            x * math.sin(.4) + y * math.cos(.4))
        angle = fit_angle(pad, pivot, 1., radius)
        self.assertAlmostEqual(angle, .4)
        self.assertGreaterEqual(pad_radius(pad, pivot, angle), radius - 1e-14)
        with self.assertRaises(ValueError):
            fit_angle(pad, pivot, 1., .2)


if __name__ == '__main__':
    unittest.main()
