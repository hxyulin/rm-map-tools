# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Directional skin policy checks independent of a native CAD installation."""
import unittest
import numpy as np
from cad_visibility_skin import directional_skin, hemisphere_views

class VisibilitySkinTests(unittest.TestCase):
    def test_rear_and_interior_removed_and_source_indices_preserved(self):
        # Front square, reversed rear square, and detached unobserved interior.
        p=np.array([[0,0,1],[1,0,1],[1,1,1],[0,1,1],[0,0,0],[1,0,0],[1,1,0],[0,1,0],[.2,.2,.5],[.4,.2,.5],[.2,.4,.5]])
        t=np.array([[0,1,2],[0,2,3],[4,6,5],[4,7,6],[8,9,10]])
        ids,proof=directional_skin(p,t,np.zeros(5,int),np.array([1,1,2,2,3]),[0,0,1],np.array([0,2]))
        np.testing.assert_array_equal(ids,[0,1]);self.assertEqual(proof['removed_units'],[2,3])
    def test_planes_do_not_cross_unit_or_material_boundaries(self):
        p=np.array([[0,0,1],[1,0,1],[0,1,1],[3,0,1],[4,0,1],[3,1,1],[6,0,1],[7,0,1],[6,1,1]])
        ids,_=directional_skin(p,np.arange(9).reshape(3,3),np.array([0,0,1]),np.array([1,2,1]),[0,0,1],np.array([0]))
        np.testing.assert_array_equal(ids,[0])
    def test_views_stay_in_front_hemisphere(self):
        f=np.array([1.,2.,3.]);v=hemisphere_views(f);self.assertEqual(v.shape,(25,3));self.assertTrue((v@f>0).all());np.testing.assert_allclose(np.linalg.norm(v,axis=1),1)
    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):hemisphere_views([0,0,0])
        with self.assertRaises(ValueError):hemisphere_views([0,0,1],[90])
        with self.assertRaises(ValueError):directional_skin(np.eye(3),np.array([[0,1,2]]),np.array([0]),np.array([1]),[0,0,1],np.array([1]))
if __name__=='__main__':unittest.main()
