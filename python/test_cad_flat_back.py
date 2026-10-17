# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Flat rear profile preserves large openings and unites overlapping panels."""
import unittest
import numpy as np
from cad_flat_back import flat_back

class FlatBackTests(unittest.TestCase):
    def test_union_and_rear_plane(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Pnt
        from cad_detail_passes import area
        def square(x,z):
            poly=BRepBuilderAPI_MakePolygon()
            for a,b in [(x,0),(x+10,0),(x+10,10),(x,10)]:poly.Add(gp_Pnt(a,b,z))
            poly.Close();return BRepBuilderAPI_MakeFace(poly.Wire()).Face()
        cap,proof=flat_back([square(0,2),square(5,4)],[0,0,1],0)
        self.assertAlmostEqual(area(cap),150);self.assertEqual(proof['result_faces'],1)
        from cad_wall_fill import shape_map
        from OCP.TopAbs import TopAbs_VERTEX
        from OCP.TopoDS import TopoDS
        from OCP.BRep import BRep_Tool
        vertices=shape_map(cap,TopAbs_VERTEX)
        for i in range(1,vertices.Extent()+1):self.assertAlmostEqual(BRep_Tool.Pnt_s(TopoDS.Vertex(vertices.FindKey(i))).Z(),0)
    def test_holes_are_selective(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Pnt,gp_Pln,gp_Dir
        from cad_detail_passes import area
        def wire(x,y,w,h):
            poly=BRepBuilderAPI_MakePolygon()
            for a,b in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]:poly.Add(gp_Pnt(a,b,0))
            poly.Close();return poly.Wire()
        maker=BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0,0,0),gp_Dir(0,0,1)),wire(0,0,100,100),True)
        from OCP.TopoDS import TopoDS
        maker.Add(TopoDS.Wire(wire(10,10,5,5).Reversed()));maker.Add(TopoDS.Wire(wire(40,40,20,20).Reversed()))
        cap,proof=flat_back([maker.Face()],[0,0,1],-3)
        self.assertAlmostEqual(area(cap),9600);self.assertEqual(sum(h['filled'] for h in proof['profiles'][0]['holes']),1)
    def test_bad_policy(self):
        with self.assertRaises(ValueError):flat_back([],np.ones(3),0)
if __name__=='__main__':unittest.main()
