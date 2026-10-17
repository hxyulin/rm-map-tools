# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Projectile-width closure keeps wider and exact-threshold apertures."""
import unittest
import numpy as np
from cad_surface_lods import profile_prism,close_bore_surfaces
from cad_wall_fill import shape_map
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir


def top_face(shape,height):
    faces=shape_map(shape,TopAbs_FACE)
    for i in range(1,faces.Extent()+1):
        face=TopoDS.Face(faces.FindKey(i));s=BRepAdaptor_Surface(face)
        if s.GetType()==GeomAbs_Plane and abs(s.Plane().Axis().Direction().Z())>.999 and abs(s.Plane().Location().Z()-height)<1e-6:return face
    raise AssertionError('missing top face')


class GapClosureTests(unittest.TestCase):
    def test_long_narrow_slot_closes_but_17mm_opening_stays(self):
        source=BRepPrimAPI_MakeBox(100,100,3).Shape()
        for origin,size in [((10,10,-1),(16,60,5)),((45,10,-1),(17,60,5)),((75,10,-1),(20,60,5))]:
            source=BRepAlgoAPI_Cut(source,BRepPrimAPI_MakeBox(gp_Pnt(*origin),*size).Shape()).Shape()
        _,proof=profile_prism(top_face(source,3),depth_mm=-3,maximum_gap_mm=17)
        closed=[x for x in proof['opening_widths'] if x['closed']];kept=[x for x in proof['opening_widths'] if not x['closed']]
        self.assertEqual(len(closed),1);self.assertGreater(closed[0]['area_mm2'],900);self.assertEqual(len(kept),2)
        self.assertAlmostEqual(closed[0]['native_width_upper_bound_mm'],16,places=5)

    def test_bore_closure_keeps_exactly_17_and_larger_diameters(self):
        source=BRepPrimAPI_MakeBox(100,40,5).Shape()
        for x,r in ((15,8),(45,8.5),(75,9)):
            source=BRepAlgoAPI_Cut(source,BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,20,-1),gp_Dir(0,0,1)),r,7).Shape()).Shape()
        result,ids,proof=close_bore_surfaces(source,maximum_gap_mm=17)
        self.assertEqual(len(proof['closed_bores']),1);self.assertAlmostEqual(proof['closed_bores'][0]['diameter_mm'],16)
        self.assertEqual(shape_map(result,TopAbs_FACE).Extent(),len(ids));self.assertGreater(proof['removed_wall_faces'],0)
        self.assertEqual(len(proof['rebuilt_end_planes']),2)

    def test_rotated_narrow_slot_uses_edge_calipers(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf,gp_Ax1,gp_Vec
        import math
        source=BRepPrimAPI_MakeBox(150,150,3).Shape();tool=BRepPrimAPI_MakeBox(gp_Pnt(-8,-30,-1),16,60,5).Shape()
        tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),math.pi/4);tr.SetTranslationPart(gp_Vec(70,70,0));tool=BRepBuilderAPI_Transform(tool,tr,True).Shape();source=BRepAlgoAPI_Cut(source,tool).Shape()
        _,proof=profile_prism(top_face(source,3),depth_mm=-3,maximum_gap_mm=17)
        self.assertEqual(len(proof['filled_hole_areas_mm2']),1)
        self.assertAlmostEqual(proof['opening_widths'][0]['native_width_upper_bound_mm'],16,places=5)

    def test_17mm_sphere_intersects_16mm_bore_but_fits_18mm_bore(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        from cad_wall_fill import volume
        source=BRepPrimAPI_MakeBox(100,40,5).Shape()
        for x,r in ((15,8),(75,9)):
            tool=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,20,-1),gp_Dir(0,0,1)),r,7).Shape();source=BRepAlgoAPI_Cut(source,tool).Shape()
        overlaps=[abs(volume(BRepAlgoAPI_Common(source,BRepPrimAPI_MakeSphere(gp_Pnt(x,20,2.5),8.5).Shape()).Shape())) for x in (15,75)]
        self.assertGreater(overlaps[0],1e-3);self.assertLess(overlaps[1],1e-8)

    def test_negative_gap_rejects(self):
        with self.assertRaises(ValueError):close_bore_surfaces(None,maximum_gap_mm=-17)


if __name__=='__main__':unittest.main()
