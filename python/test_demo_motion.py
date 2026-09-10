# SPDX-License-Identifier: MIT OR Apache-2.0
import unittest
from preview.motion_profiles import demo_coordinate


class DemoMotionTests(unittest.TestCase):
    def setUp(self):
        self.joint = {'limits': [-.28, .28], 'demo_motion': {
            'type': 'sinusoidal', 'demo_only': True, 'when': 'no_target_mode',
            'period_s': 4, 'range': 'joint_limits'}}

    def test_demo_reaches_both_rulebook_endpoints_and_loops(self):
        for time, expected in [(0, 0), (1, .28), (2, 0), (3, -.28), (4, 0)]:
            self.assertAlmostEqual(demo_coordinate(self.joint, time), expected)

    def test_demo_yields_to_every_target_mode(self):
        for mode in ['fixed_target', 'random_fixed_target', 'random_moving_target', 'terminal_moving_target']:
            self.assertIsNone(demo_coordinate(self.joint, 1, mode))
        self.assertIsNone(demo_coordinate({}, 1))

    def test_invalid_period_is_not_accepted(self):
        self.joint['demo_motion']['period_s'] = 0
        with self.assertRaises(ValueError):
            demo_coordinate(self.joint, 1)
