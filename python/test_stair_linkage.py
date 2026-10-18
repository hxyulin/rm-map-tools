# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-fit linkage regression without loading CAD or generated assets."""
import unittest
import numpy as np
from stair_linkage import C, DEPLOYED_RAD, TRAVEL_RAD, frames, FRONT, COUPLER, SLIDER, GUIDE, REAR, WHEELS, group


class StairLinkageTests(unittest.TestCase):
    def test_closed_lengths_and_level_wheels(self):
        for angle in np.linspace(0, DEPLOYED_RAD-TRAVEL_RAD, 129):
            pose = frames(angle)
            p = {name:C@value[:3,3] for name,value in pose.items()}
            self.assertAlmostEqual(np.linalg.norm(p['front']-p['coupler']), .130)
            self.assertAlmostEqual(np.linalg.norm(p['coupler']-p['rear']), .200)
            self.assertAlmostEqual(np.linalg.norm(p['front']-p['wheel-0'] + np.array([0,.2083,0])), .190)
            for value in pose.values():
                np.testing.assert_allclose(value[:3,:3].T@value[:3,:3], np.eye(3), atol=1e-12)
        p=frames(0)
        self.assertAlmostEqual(p['wheel-0'][1,3],p['wheel-2'][1,3])

    def test_disjoint_reviewed_membership(self):
        sets=[FRONT,COUPLER,SLIDER,GUIDE,REAR,set(WHEELS)]
        for i,a in enumerate(sets):
            for b in sets[i+1:]:self.assertFalse(a&b, a&b)
        for i,name in WHEELS.items():self.assertEqual(group(f'1/1/1/{i}'),name)
        self.assertEqual(group('1/1/3'),'slider')
        self.assertEqual(group('1/1/1/126'),'guide')
        self.assertEqual(group('1/1/1/127'),'guide')
        self.assertEqual(group('1/2/1'),'body')


if __name__ == '__main__':unittest.main()
