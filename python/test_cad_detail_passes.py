# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Finite native containment, cavity closure and bounded bore regression tests."""
import unittest
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakeSphere
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir
from OCP.TopAbs import TopAbs_FACE
from cad_wall_fill import shape_map,volume
from cad_detail_passes import enclosed,fill_enclosed_voids,small_bore_groups,smooth_bores


class DetailPassTests(unittest.TestCase):
    def test_strict_containment_rejects_visible_and_touching_parts(self):
        outer=BRepPrimAPI_MakeBox(10,10,10).Shape()
        inner=BRepPrimAPI_MakeBox(gp_Pnt(2,2,2),1,1,1).Shape()
        self.assertTrue(enclosed(inner,outer)['accepted'])
        self.assertFalse(enclosed(BRepPrimAPI_MakeBox(gp_Pnt(9.5,2,2),1,1,1).Shape(),outer)['accepted'])
        self.assertFalse(enclosed(BRepPrimAPI_MakeBox(gp_Pnt(0,2,2),1,1,1).Shape(),outer)['accepted'])

    def test_enclosure_respects_air_in_an_opaque_solid(self):
        box=BRepPrimAPI_MakeBox(10,10,10).Shape();air=BRepPrimAPI_MakeSphere(gp_Pnt(5,5,5),2).Shape();hollow=BRepAlgoAPI_Cut(box,air).Shape()
        inside_air=BRepPrimAPI_MakeBox(gp_Pnt(4.8,4.8,4.8),.4,.4,.4).Shape()
        self.assertFalse(enclosed(inside_air,hollow)['accepted'])

    def test_enclosed_voids_retain_every_exterior_face_identity_and_paint(self):
        box=BRepPrimAPI_MakeBox(10,10,10).Shape();source=BRepAlgoAPI_Cut(box,BRepPrimAPI_MakeSphere(gp_Pnt(5,5,5),2).Shape()).Shape()
        faces=shape_map(source,TopAbs_FACE);colours=tuple(str(i) for i in range(faces.Extent()))
        result=fill_enclosed_voids(source,colours)
        self.assertEqual(result.proof['removed_cavity_shells'],1);self.assertEqual(result.proof['result_faces'],6)
        self.assertAlmostEqual(volume(result.shape),1000)
        output=shape_map(result.shape,TopAbs_FACE)
        for i,ids in enumerate(result.source_face_indices,1):
            self.assertTrue(output.FindKey(i).IsSame(faces.FindKey(ids[0])))
            self.assertEqual(result.face_colours[i-1],colours[ids[0]-1])

    def test_plain_bore_discovery_and_smoothing_preserves_material(self):
        box=BRepPrimAPI_MakeBox(10,10,4).Shape();hole=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5,5,-1),gp_Dir(0,0,1)),1,6).Shape();source=BRepAlgoAPI_Cut(box,hole).Shape()
        groups=small_bore_groups(source,maximum_radius_mm=1.1);self.assertEqual(len(groups),1)
        faces=shape_map(source,TopAbs_FACE);colours=['gray']*faces.Extent();colours[0]='red'
        result=smooth_bores(source,colours,groups,maximum_added_volume_mm3=20)
        self.assertEqual(result.proof['result_faces'],6);self.assertAlmostEqual(volume(result.shape),400)
        self.assertAlmostEqual(result.proof['removed_volume_mm3'],0);self.assertAlmostEqual(result.proof['added_outside_feature_boxes_mm3'],0)
        self.assertIn('red',result.face_colours)

    def test_countersink_is_left_as_an_unresolved_feature(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
        source=BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(10,10,4).Shape(),BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5,5,-1),gp_Dir(0,0,1)),1,6).Shape()).Shape()
        source=BRepAlgoAPI_Cut(source,BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(5,5,3),gp_Dir(0,0,1)),1,2,1).Shape()).Shape()
        self.assertEqual(small_bore_groups(source),[])

    def test_invalid_outer_shell_is_not_repaired_or_accepted(self):
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Shell
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
        faces=shape_map(BRepPrimAPI_MakeBox(10,10,10).Shape(),TopAbs_FACE);builder=BRep_Builder();shell=TopoDS_Shell();builder.MakeShell(shell)
        for i in range(1,6):builder.Add(shell,faces.FindKey(i))
        source=BRepBuilderAPI_MakeSolid(shell).Solid()
        with self.assertRaisesRegex(ValueError,'outer shell'):fill_enclosed_voids(source,['gray']*5)

    def test_radius_budget_protects_large_functional_openings(self):
        source=BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(20,20,4).Shape(),BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(10,10,-1),gp_Dir(0,0,1)),5,6).Shape()).Shape()
        self.assertEqual(small_bore_groups(source,maximum_radius_mm=3),[])

    def test_invalid_appearance_and_added_volume_budgets_are_rejected(self):
        source=BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(10,10,4).Shape(),BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5,5,-1),gp_Dir(0,0,1)),1,6).Shape()).Shape();groups=small_bore_groups(source)
        with self.assertRaises(ValueError):fill_enclosed_voids(source,[])
        with self.assertRaises(ValueError):smooth_bores(source,['x']*shape_map(source,TopAbs_FACE).Extent(),groups,maximum_added_volume_mm3=1)
        with self.assertRaises(ValueError):enclosed(source,source,clearance_mm=0)


class NativeDetailMeshTests(unittest.TestCase):
    def test_coarser_angular_sampling_preserves_faces_and_paint(self):
        from cad_detail_passes import mesh_native_detail
        shape=BRepPrimAPI_MakeCylinder(3,4).Shape();colours=['0.5,0.5,0.5']*shape_map(shape,TopAbs_FACE).Extent()
        first=mesh_native_detail(shape,colours,linear_deflection_mm=.1,angular_deflection_rad=.25)
        coarse=mesh_native_detail(shape,colours,linear_deflection_mm=.1,angular_deflection_rad=.6)
        self.assertLess(len(coarse[1]),len(first[1]));self.assertEqual(set(coarse[3]),set(first[3]));self.assertEqual(set(coarse[2]),{'0.5000,0.5000,0.5000'})
        # Clearing cached triangulations makes returning to the finer request stable.
        again=mesh_native_detail(shape,colours,linear_deflection_mm=.1,angular_deflection_rad=.25)
        self.assertEqual(len(again[1]),len(first[1]))

class ConstructivePlugTests(unittest.TestCase):
    def source(self):
        return BRepAlgoAPI_Cut(BRepPrimAPI_MakeBox(10,10,4).Shape(),BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5,5,-1),gp_Dir(0,0,1)),1,6).Shape()).Shape()

    def test_native_plugs_are_flush_additive_and_preserve_paint(self):
        from cad_detail_passes import plug_bores
        from OCP.BRepBndLib import BRepBndLib
        from OCP.Bnd import Bnd_Box
        source=self.source();colours=['0.5,0.5,0.5']*shape_map(source,TopAbs_FACE).Extent();colours[0]='1,0,0'
        result=plug_bores(source,colours,small_bore_groups(source),maximum_added_volume_mm3=20)
        self.assertAlmostEqual(volume(result.shape),400);self.assertAlmostEqual(volume(BRepAlgoAPI_Cut(source,result.shape).Shape()),0)
        self.assertEqual(result.proof['result_faces'],6);self.assertIn('1,0,0',result.face_colours)
        box=Bnd_Box();BRepBndLib.AddOptimal_s(result.shape,box,False,False)
        self.assertAlmostEqual(box.CornerMin().Z(),0);self.assertAlmostEqual(box.CornerMax().Z(),4)
        bad=[{**small_bore_groups(source)[0],'radius_mm':.5}]
        with self.assertRaises(ValueError):plug_bores(source,colours,bad,maximum_added_volume_mm3=20)

    def test_split_cylinder_faces_form_one_complete_feature(self):
        from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideAngle
        from OCP.BRepCheck import BRepCheck_Analyzer
        from cad_detail_passes import plug_bores
        import numpy as np
        split=ShapeUpgrade_ShapeDivideAngle(np.pi/2,self.source());split.Perform();source=split.Result()
        self.assertTrue(BRepCheck_Analyzer(source).IsValid());groups=small_bore_groups(source)
        self.assertEqual(len(groups),1);self.assertGreater(len(groups[0]['face_indices']),1)
        result=plug_bores(source,['0.5,0.5,0.5']*shape_map(source,TopAbs_FACE).Extent(),groups,maximum_added_volume_mm3=20)
        self.assertAlmostEqual(volume(result.shape),400)

    def test_native_mesh_support_check_and_limit_rejection(self):
        from cad_detail_passes import mesh_native_detail,sampled_support_error
        shape=BRepPrimAPI_MakeCylinder(3,4).Shape();mesh=mesh_native_detail(shape,['0.5,0.5,0.5']*shape_map(shape,TopAbs_FACE).Extent())
        proof=sampled_support_error(shape,mesh[0],mesh[1],mesh[3],limit_mm=.12)
        self.assertLessEqual(proof['maximum_sampled_support_error_mm'],.12)
        with self.assertRaises(ValueError):sampled_support_error(shape,mesh[0]+[10,0,0],mesh[1],mesh[3],limit_mm=.12)

if __name__=='__main__':unittest.main()
