# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""The source-fitted EGA followers must close at both pins over the whole motion."""
import copy
import importlib.util
from pathlib import Path
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / 'benchmarks/2026-10-18-team-robot/bind_sentry.py'
spec = importlib.util.spec_from_file_location('ega_sentry', SCRIPT)
ega = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ega)


class EgaLinkageTests(unittest.TestCase):
    def fixture(self):
        return ega.linkage_joints(np.array([0.,0.,.0122]), np.array([0.,0.,.1372]))

    def test_pitch_and_uwb_followers_close_through_folding_and_aiming(self):
        report = ega.validate_linkages(self.fixture())
        self.assertLess(report['max_rod_endpoint_error_m'], 1e-12)

    def test_source_axis_collision_box_encloses_every_vertex_without_filling_corners(self):
        from itertools import product
        from scipy.spatial.transform import Rotation
        basis = Rotation.from_euler('z', -32., degrees=True).as_matrix()
        points = np.array(list(product([-0.29,0.29],[-0.29,0.29],[-0.1,0.1]))) @ basis.T
        box = ega.collision_box(points,np.zeros(3),chassis=True)
        q = np.array(box['rotation_wxyz'])
        axes = Rotation.from_quat(q[[1,2,3,0]]).as_matrix()
        enclosed = (points-box['center_m']) @ axes
        self.assertLessEqual(float(np.max(np.abs(enclosed)-box['half_m'])),1e-12)
        old = ega.collision_box(points,np.zeros(3))
        self.assertLess(np.prod(box['half_m']),np.prod(old['half_m'])*0.8)

    def test_old_independent_uwb_hinge_is_rejected(self):
        joints = self.fixture()
        joints[8]['parent'] = 1
        joints[8]['angle_rad'] = np.deg2rad(110)
        with self.assertRaisesRegex(ValueError, 'closure violated'):
            ega.validate_linkages(joints)

    def test_pitch_rod_on_the_lift_instead_of_lower_crank_is_rejected(self):
        joints = copy.deepcopy(self.fixture())
        joints[7]['parent'] = 2
        with self.assertRaisesRegex(ValueError, 'closure violated'):
            ega.validate_linkages(joints)

    def test_reviewed_source_ownership_separates_moving_and_fixed_pins(self):
        for path,name in [('1/12/31','lower-pitch'),('1/12/33','pitch-rod'),
                          ('1/12/55','lift'),('1/12/59','uwb-rod'),
                          ('1/12/54','uwb-carrier'),('1/12/70','yaw')]:
            self.assertEqual(ega.anatomy(path), name)


if __name__ == '__main__':
    unittest.main()
