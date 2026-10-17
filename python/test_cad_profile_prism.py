# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check real through-openings versus backed recesses in projected plate profiles."""
import unittest
from cad_profile_prism import projected_prism
from cad_wall_fill import shape_map,volume
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Ax2,gp_Pnt,gp_Dir
import math


def horizontal_faces(shape):
    result=[];faces=shape_map(shape,TopAbs_FACE)
    for i in range(1,faces.Extent()+1):
        face=TopoDS.Face(faces.FindKey(i));s=BRepAdaptor_Surface(face)
        if s.GetType()==GeomAbs_Plane and abs(s.Plane().Axis().Direction().Z())>.999999:result.append(face)
    return result


class ProfilePrismTests(unittest.TestCase):
    def test_through_hole_survives_but_a_backed_recess_closes(self):
        box=BRepPrimAPI_MakeBox(10,10,4).Shape();hole=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5,5,0),gp_Dir(0,0,1)),2,4).Shape();source=BRepAlgoAPI_Cut(box,hole).Shape();faces=horizontal_faces(source)
        prism,proof=projected_prism(faces,[0,0,1],4,4)
        self.assertAlmostEqual(volume(prism),400-16*math.pi,places=5)
        self.assertTrue(proof['valid_solid']);self.assertLessEqual(proof['maximum_lateral_shift_mm'],.001)
        # An intact intermediate layer genuinely backs the circular recess.
        backed,_=projected_prism(faces+horizontal_faces(box),[0,0,1],4,4)
        self.assertAlmostEqual(volume(backed),400,places=5)
        self.assertAlmostEqual(volume(source),400-16*math.pi,places=5)
        with self.assertRaises(ValueError):projected_prism(faces,[0,0,0],4,4)
        with self.assertRaises(ValueError):projected_prism(faces,[0,0,1],4,2)
