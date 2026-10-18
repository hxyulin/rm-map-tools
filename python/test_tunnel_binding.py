# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reviewed source membership and serial-frame invariants without CAD inputs."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
spec=importlib.util.spec_from_file_location('binding',Path(__file__).resolve().parents[1]/'benchmarks/2026-10-18-team-robot/bind_tunnel.py')
binding=importlib.util.module_from_spec(spec);spec.loader.exec_module(binding)


class TunnelBindingTests(unittest.TestCase):
    def tearDown(self):binding.PROFILE='heavy'
    def test_leads_only_are_cut_and_source_hardware_stays(self):
        binding.PROFILE='heavy'
        self.assertIsNone(binding.anatomy('1/1/3/10/2/5'))
        self.assertEqual(binding.anatomy('1/1/3/10/3/5'),'source-body')
        self.assertEqual(binding.anatomy('1/1/3/1'),'wheel-0')
        self.assertEqual(binding.anatomy('1/2/6/1/1'),'camera-lift')
        self.assertEqual(binding.anatomy('1/2/5/2'),'uwb')
    def test_fixed_yaw_membership_matches_full_path_components(self):
        binding.PROFILE='infantry'
        self.assertEqual(binding.anatomy('1/302/6/2'),'source-body')
        self.assertEqual(binding.anatomy('1/302/6/20'),'yaw')
        self.assertEqual(binding.anatomy('1/302/14'),'pitch')
        self.assertEqual(binding.anatomy('1/3/2/1'),'wheel-0')
    def test_counter_rotation_preserves_forearm_orientation(self):
        axis=np.array([.999594,0,-.0284937]);axis/=np.linalg.norm(axis)
        joints=[binding.joint('shoulder',None,[0,.2,0],axis,-np.deg2rad(7)),
                binding.joint('elbow',0,[0,.25,-.38],axis,np.deg2rad(7))]
        for fraction in np.linspace(0,1,20):
            frames=binding.poses(joints,fraction)
            np.testing.assert_allclose(frames[1][:3,:3],np.eye(3),atol=1e-12)
            self.assertTrue(np.isfinite(frames).all())


if __name__=='__main__':unittest.main()
