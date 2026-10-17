# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Native checks for bounded wall fills, profile retention and paint barriers."""
import unittest
import numpy as np
from cad_wall_fill import WallPanel,FaceProfilePanel,fill_wall,shape_map,volume
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
from OCP.gp import gp_Pnt,gp_Vec
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.TopAbs import TopAbs_FACE,TopAbs_WIRE
from OCP.TopoDS import TopoDS

GRAY='0.5,0.5,0.5'


def perforated():
    source=BRepPrimAPI_MakeBox(100,5,50).Shape()
    for x in (10,40,70):source=BRepAlgoAPI_Cut(source,BRepPrimAPI_MakeBox(gp_Pnt(x,-1,10),10,7,30).Shape()).Shape()
    return source


def apply(source,panel,limit=10000,colours=None):
    return fill_wall(source,panel,colours or [GRAY]*shape_map(source,TopAbs_FACE).Extent(),max_added_volume_mm3=limit)


class WallFillTests(unittest.TestCase):
    def test_grille_becomes_six_faces_without_material_removal(self):
        source=perforated();before=volume(source)
        r=apply(source,WallPanel((0,0,0),tuple(map(tuple,np.eye(3))),(100,5,50),GRAY))
        self.assertEqual(r.proof['result_faces'],6);self.assertAlmostEqual(volume(source),before)
        self.assertAlmostEqual(r.proof['added_volume_mm3'],4500)
        self.assertEqual(r.proof['removed_volume_mm3'],0);self.assertEqual(r.proof['added_outside_panel_volume_mm3'],0)
        self.assertEqual(r.face_colours,(GRAY,)*6)

    def test_source_outer_profile_retains_chamfers(self):
        polygon=BRepBuilderAPI_MakePolygon()
        for p in ((0,0,0),(100,0,0),(100,0,40),(90,0,50),(10,0,50),(0,0,40)):polygon.Add(gp_Pnt(*p))
        polygon.Close();source=BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(polygon.Wire()).Face(),gp_Vec(0,5,0)).Shape()
        source=BRepAlgoAPI_Cut(source,BRepPrimAPI_MakeBox(gp_Pnt(40,-1,10),10,7,30).Shape()).Shape()
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        faces=shape_map(source,TopAbs_FACE)
        for i in range(1,faces.Extent()+1):
            face=TopoDS.Face(faces.FindKey(i))
            if shape_map(face,TopAbs_WIRE).Extent()>1:
                # Select the signed depth that enters this explicitly known 5 mm plate.
                for depth in (-5.00001,5.00001):
                    panel=FaceProfilePanel(face,depth,GRAY)
                    if volume(BRepAlgoAPI_Common(source,panel.shape()).Shape())>1000:break
                break
        r=apply(source,panel)
        self.assertAlmostEqual(volume(r.shape),24500,delta=.06)
        self.assertEqual(r.proof['result_faces'],8)

    def test_bridge_only_selected_notched_foot_strip(self):
        source=BRepPrimAPI_MakeBox(100,10,30).Shape()
        for x in (10,40,70):source=BRepAlgoAPI_Cut(source,BRepPrimAPI_MakeBox(gp_Pnt(x,-1,-1),20,12,11).Shape()).Shape()
        faces=shape_map(source,TopAbs_FACE)
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        candidates=[]
        for i in range(1,faces.Extent()+1):
            f=TopoDS.Face(faces.FindKey(i));surf=BRepAdaptor_Surface(f)
            if abs(surf.Plane().Axis().Direction().Y())>.99:candidates.append(f)
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        for face in candidates:
            for depth in (-10.00001,10.00001):
                p=FaceProfilePanel(face,depth,GRAY,'convex-hull')
                if volume(BRepAlgoAPI_Common(source,p.shape()).Shape())>1000:break
            else:continue
            break
        r=apply(source,p,limit=10000)
        self.assertAlmostEqual(r.proof['added_volume_mm3'],6000,delta=.1)
        self.assertLessEqual(r.proof['result_faces'],10)

    def test_window_closes_one_hole_and_keeps_other_openings(self):
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.TopAbs import TopAbs_IN,TopAbs_OUT
        source=perforated();faces=shape_map(source,TopAbs_FACE)
        for i in range(1,faces.Extent()+1):
            face=TopoDS.Face(faces.FindKey(i))
            if shape_map(face,TopAbs_WIRE).Extent()>1:break
        frame=BRepAdaptor_Surface(face).Plane().Position()
        origin=np.array([frame.Location().X(),frame.Location().Y(),frame.Location().Z()])
        axes=np.array([[v.X(),v.Y(),v.Z()] for v in (frame.XDirection(),frame.YDirection(),frame.Direction())])
        uv=(np.array([[5,origin[1],5],[25,origin[1],45]])-origin)@axes.T
        lo=uv.min(0);hi=uv.max(0);window=(lo[0],lo[1],hi[0],hi[1])
        for depth in (-5.00001,5.00001):
            panel=FaceProfilePanel(face,depth,GRAY,'outer-wire',window)
            if volume(BRepAlgoAPI_Common(source,panel.shape()).Shape())>100:break
        r=apply(source,panel,limit=1600)
        self.assertAlmostEqual(r.proof['added_volume_mm3'],1500,delta=.1)
        self.assertEqual(BRepClass3d_SolidClassifier(r.shape,gp_Pnt(15,2.5,20),1e-7).State(),TopAbs_IN)
        self.assertEqual(BRepClass3d_SolidClassifier(r.shape,gp_Pnt(45,2.5,20),1e-7).State(),TopAbs_OUT)

    def test_conflicting_material_boundaries_survive_unification(self):
        source=perforated();faces=shape_map(source,TopAbs_FACE);colours=[GRAY]*faces.Extent();colours[0]='1,0,0'
        r=apply(source,WallPanel((0,0,0),tuple(map(tuple,np.eye(3))),(100,5,50),GRAY),colours=colours)
        self.assertIn('1,0,0',r.face_colours)
        for colour,ids in zip(r.face_colours,r.source_face_indices):
            self.assertTrue(all(colours[i-1]==colour for i in ids))

    def test_reject_disconnected_empty_and_over_budget_fills(self):
        source=perforated();axes=tuple(map(tuple,np.eye(3)))
        with self.assertRaisesRegex(ValueError,'overlap'):apply(source,WallPanel((200,0,0),axes,(100,5,50),GRAY))
        with self.assertRaisesRegex(ValueError,'budget'):apply(source,WallPanel((0,0,0),axes,(100,5,50),GRAY),limit=100)
        with self.assertRaisesRegex(ValueError,'empty'):apply(BRepPrimAPI_MakeBox(100,5,50).Shape(),WallPanel((0,0,0),axes,(100,5,50),GRAY))

    def test_invalid_frame_and_source_profile_refused(self):
        with self.assertRaises(ValueError):WallPanel((0,0,0),((1,0,0),(1,0,0),(0,0,1)),(1,1,1),GRAY).shape()
        with self.assertRaises(ValueError):WallPanel((0,0,0),tuple(map(tuple,np.eye(3))),(1,1,-1),GRAY).shape()
        with self.assertRaises(ValueError):FaceProfilePanel(TopoDS.Face(shape_map(BRepPrimAPI_MakeBox(1,1,1).Shape(),TopAbs_FACE).FindKey(1)),1,GRAY).shape()

if __name__=='__main__':unittest.main()
