# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explicit profile filling must honor measured guards and closed topology."""
import unittest
import numpy as np
from cad_profile_envelope import profile_envelope
from test_cad_collision_proxy import cube,subdivide


class ProfileEnvelopeTests(unittest.TestCase):
    def test_rotated_box_becomes_a_closed_profile_prism(self):
        p,t=subdivide(*cube());a=.37;rotation=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]]);p=p@rotation.T+[123.456,10,20];before=p.copy();q,f,proof=profile_envelope(p,t,rotation[:,0],maximum_surface_distance_mm=.01)
        self.assertEqual(len(f),12);self.assertTrue(proof['topology']['closed_oriented_manifold']);self.assertAlmostEqual(proof['depth_mm'],20);np.testing.assert_array_equal(p,before)

    def test_filling_an_open_back_requires_an_explicit_larger_allowance(self):
        p,t=cube();t=t[2:]
        with self.assertRaises(ValueError):profile_envelope(p,t,[1,0,0],maximum_surface_distance_mm=3)
        q,f,proof=profile_envelope(p,t,[1,0,0],maximum_surface_distance_mm=21)
        self.assertGreater(proof['maximum_sampled_distance_mm'],3)

    def test_invalid_policy_rejected(self):
        p,t=cube()
        with self.assertRaises(ValueError):profile_envelope(p,t,[0,0,0])
        with self.assertRaises(ValueError):profile_envelope(p,t,[1,0,0],boundary_error_mm=float('nan'))


if __name__=='__main__':unittest.main()
