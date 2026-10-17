# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Finite panel surgery preserves disjoint geometry and nonselected materials."""
import unittest
import numpy as np
from cad_panel_replace import clip_panel_mesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox


class PanelReplaceTests(unittest.TestCase):
    def test_finite_inside_and_material_protection(self):
        tri=np.array([[[.1,.1,.5],[.9,.1,.5],[.1,.9,.5]],[[2,0,.5],[3,0,.5],[2,1,.5]],[[.1,.1,.6],[.9,.1,.6],[.1,.9,.6]]]);c=np.array([[.2]*3,[.2]*3,[.6275]*3]);p,t,cc,proof=clip_panel_mesh(tri.reshape(-1,3),np.arange(9).reshape(-1,3),c,BRepPrimAPI_MakeBox(1,1,1).Solid());self.assertEqual(proof['removed_input_triangle_indices'],[0]);np.testing.assert_array_equal(p[t],tri[1:]);np.testing.assert_array_equal(cc,c[1:])

    def test_crossing_triangle_is_cut_not_discarded(self):
        p=np.array([[-1,.5,.5],[2,.5,.5],[.5,2,.5]]);q,t,c,proof=clip_panel_mesh(p,np.array([[0,1,2]]),np.array([[.2]*3]),BRepPrimAPI_MakeBox(1,1,1).Solid());self.assertEqual(len(proof['partial_triangles']),1);self.assertTrue(np.all(q[t].mean(1)[:,1]>=.5));old=np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0]))/2;g=q[t];area=np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).sum()/2;self.assertGreater(area,0);self.assertLess(area,old);self.assertEqual(proof['removed_input_triangle_indices'],[])

    def test_invalid_mesh_rejected(self):
        with self.assertRaises(ValueError):clip_panel_mesh(np.zeros((3,3)),np.array([[0,1,9]]),np.zeros((1,3)),BRepPrimAPI_MakeBox(1,1,1).Solid())

if __name__=='__main__':unittest.main()
