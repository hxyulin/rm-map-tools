# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Centroid density accounting independent of placement count or triangle area."""
import unittest
import numpy as np
from triangle_density import centroid_grid


class TriangleDensityTests(unittest.TestCase):
    def test_negative_coordinates_and_closed_upper_boundary(self):
        centers=np.array([[-1,-1,0],[-.75,-.75,0],[0,0,3],[1,1,0]])
        tris=np.repeat(centers[:,None,:],3,axis=1)
        grid=centroid_grid(tris,lower_m=(-1,-1),upper_m=(1,1),cell_size_m=.5)
        self.assertEqual(grid.shape,(4,4));self.assertEqual(grid.sum(),4)
        self.assertEqual(grid[0,0],2);self.assertEqual(grid[2,2],1);self.assertEqual(grid[3,3],1)

    def test_placed_copies_and_vertical_surfaces_are_each_counted(self):
        triangle=np.array([[[0,0,0],[0,0,2],[0,.4,2]]],float)
        copies=np.concatenate([triangle,triangle+[2,0,0],triangle])
        grid=centroid_grid(copies,lower_m=(-1,-1),upper_m=(3,1))
        self.assertEqual(grid.sum(),3);self.assertEqual(grid.max(),2)
        self.assertEqual(np.count_nonzero(grid),2)

    def test_empty_input_has_stable_extent(self):
        grid=centroid_grid(np.empty((0,3,3)),lower_m=(0,0),upper_m=(1,2))
        self.assertEqual(grid.shape,(4,2));self.assertEqual(grid.sum(),0)

    def test_invalid_or_outside_geometry_is_not_dropped(self):
        for tris,lower,upper,cell in [(np.zeros((1,3,2)),(0,0),(1,1),.5),(np.full((1,3,3),np.nan),(0,0),(1,1),.5),(np.zeros((1,3,3)),(0,0),(0,1),.5),(np.zeros((1,3,3)),(0,0),(1,1),0),(np.full((1,3,3),2),(0,0),(1,1),.5)]:
            with self.assertRaises(ValueError):centroid_grid(tris,lower_m=lower,upper_m=upper,cell_size_m=cell)

if __name__=='__main__':unittest.main()
