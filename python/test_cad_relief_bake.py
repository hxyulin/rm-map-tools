# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source appearance, coverage, normal convention and height invariants."""
import unittest
import numpy as np
from cad_relief_bake import bake_relief


class ReliefBakeTests(unittest.TestCase):
    def test_frontmost_colour_and_height_on_rotated_plate(self):
        local=np.array([[0,0,0],[2,0,0],[2,2,0],[0,2,0],[.5,.5,1],[1.5,.5,1],[1.5,1.5,1],[.5,1.5,1]])
        frame=np.array([[0,1,0],[0,0,1],[1,0,0]]);origin=np.array([1000,2000,3000]);p=local@frame+origin;t=np.array([[0,1,2],[0,2,3],[4,5,6],[4,6,7]]);colors=np.array([[.2,.3,.4]]*2+[[1,0,0]]*2)
        r=bake_relief(p,t,colors,origin_mm=origin,axes=frame,bounds_uv_mm=[0,0,2,2],resolution=32)
        np.testing.assert_array_equal(r['normal_rgb_linear'][16,16],[128,128,255]);np.testing.assert_array_equal(r['base_colour_rgba'][16,16],[255,0,0,255]);self.assertEqual(r['height_mm'][16,16],1);self.assertEqual(r['height_mm'][0,0],0)
        self.assertTrue(np.all(r['source_triangle_owner']>=0))

    def test_holes_are_transparent_and_empty_heights_are_nan(self):
        p=np.array([[0,0,0],[1,0,0],[0,1,0]]);r=bake_relief(p,[[0,1,2]],[[.5,.5,.5]],origin_mm=[0,0,0],axes=np.eye(3),bounds_uv_mm=[0,0,2,2],resolution=16)
        self.assertEqual(r['base_colour_rgba'][0,-1,3],0);self.assertTrue(np.isnan(r['height_mm'][0,-1]));self.assertEqual(r['source_triangle_owner'][0,-1],-1)

    def test_invalid_frame_rejected(self):
        with self.assertRaises(ValueError):bake_relief([[0,0,0]],[[0,0,0]],[[0,0,0]],origin_mm=[0,0,0],axes=np.zeros((3,3)),bounds_uv_mm=[0,0,1,1])


if __name__=='__main__':unittest.main()
