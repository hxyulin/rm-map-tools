# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Selected axial closure respects stepped mouths, complete topology and limits."""
import unittest
import numpy as np
from cad_surface_lods import close_selected_axial_bores,cap_selected_recess_mesh
from cad_wall_fill import shape_map
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakeCone
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
from OCP.BRepTools import BRepTools
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_FACE,TopAbs_WIRE,TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir


def fixture(large=3.75,blind=False,conical=False):
    s=BRepPrimAPI_MakeBox(60,40,8).Shape()
    for x in (15,45):
        s=BRepAlgoAPI_Cut(s,BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,20,2 if blind else -1),gp_Dir(0,0,1)),2.1,10).Shape()).Shape()
    tool=(BRepPrimAPI_MakeCone if conical else BRepPrimAPI_MakeCylinder)
    args=(2.1,large,4) if conical else (large,4)
    s=BRepAlgoAPI_Cut(s,tool(gp_Ax2(gp_Pnt(15,20,5),gp_Dir(0,0,1)),*args).Shape()).Shape()
    ff=shape_map(s,TopAbs_FACE)
    for i in range(1,ff.Extent()+1):
        face=TopoDS.Face(ff.FindKey(i));surface=BRepAdaptor_Surface(face)
        if surface.GetType()!=GeomAbs_Plane or abs(surface.Plane().Axis().Direction().Z())<.999 or abs(surface.Plane().Location().Z())>1e-6:continue
        ww=shape_map(face,TopAbs_WIRE);outer=BRepTools.OuterWire_s(face)
        for j in range(1,ww.Extent()+1):
            wire=ww.FindKey(j)
            if wire.IsSame(outer):continue
            ee=shape_map(wire,TopAbs_EDGE);circle=BRepAdaptor_Curve(TopoDS.Edge(ee.FindKey(1))).Circle()
            if abs(circle.Location().X()-15)<1e-6:return s,i,j
    # For blind geometry select the top mouth instead.
    for i in range(1,ff.Extent()+1):
        face=TopoDS.Face(ff.FindKey(i));surface=BRepAdaptor_Surface(face)
        if surface.GetType()==GeomAbs_Plane and abs(surface.Plane().Location().Z()-8)<1e-6:
            ww=shape_map(face,TopAbs_WIRE);outer=BRepTools.OuterWire_s(face)
            for j in range(1,ww.Extent()+1):
                if not ww.FindKey(j).IsSame(outer):return s,i,j
    raise AssertionError('fixture entry missing')


class AxialBoreTests(unittest.TestCase):
    def test_closes_one_stepped_bore_and_preserves_other_native_faces(self):
        s,i,j=fixture();original=shape_map(s,TopAbs_FACE);result,ids,proof=close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=[j],maximum_gap_mm=17)
        self.assertEqual(len(proof['closed_bores']),1);b=proof['closed_bores'][0];self.assertEqual(b['radii_mm'],[2.1,3.75]);self.assertEqual(len(b['shoulder_face_indices']),1);self.assertEqual(len(b['end_mouths']),2)
        faces=shape_map(result,TopAbs_FACE);self.assertEqual(faces.Extent(),len(ids));self.assertEqual(len(proof['removed_wall_and_shoulder_faces']),3)
        for k,source in enumerate(ids,1):
            if source not in proof['rebuilt_end_planes']:self.assertTrue(faces.FindKey(k).IsSame(original.FindKey(source)))
        # The neighboring unselected through-hole remains in both exterior planes.
        for source in proof['rebuilt_end_planes']:
            face=faces.FindKey(ids.index(source)+1);self.assertTrue(BRepCheck_Analyzer(face).IsValid());self.assertEqual(shape_map(face,TopAbs_WIRE).Extent(),2)

    def test_oversize_and_exact_threshold_counterbores_reject(self):
        for radius in (8.5,9):
            with self.subTest(radius=radius):
                s,i,j=fixture(large=radius)
                with self.assertRaises(ValueError):close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=[j],maximum_gap_mm=17)

    def test_below_threshold_counterbore_accepts(self):
        s,i,j=fixture(large=8)
        _,_,p=close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=[j],maximum_gap_mm=17);self.assertEqual(p['closed_bores'][0]['radii_mm'],[2.1,8.0])

    def test_blind_bore_rejects(self):
        s,i,j=fixture(blind=True)
        with self.assertRaises(ValueError):close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=[j],maximum_gap_mm=17)

    def test_coaxial_conical_transition_accepts(self):
        s,i,j=fixture(conical=True)
        _,_,proof=close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=[j],maximum_gap_mm=17)
        self.assertEqual(len(proof['closed_bores']),1)
        self.assertGreater(max(proof['closed_bores'][0]['radii_mm']),2.1)

    def test_multiple_selected_bores_share_rebuilt_end_planes(self):
        s,i,j=fixture();ff=shape_map(s,TopAbs_FACE);face=TopoDS.Face(ff.FindKey(i));ww=shape_map(face,TopAbs_WIRE);outer=BRepTools.OuterWire_s(face);selected=[k for k in range(1,ww.Extent()+1) if not ww.FindKey(k).IsSame(outer)]
        result,ids,proof=close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=selected,maximum_gap_mm=17)
        self.assertEqual(len(proof['closed_bores']),2);out=shape_map(result,TopAbs_FACE)
        for source in proof['rebuilt_end_planes']:self.assertEqual(shape_map(out.FindKey(ids.index(source)+1),TopAbs_WIRE).Extent(),1)

    def test_rigid_transform_preserves_bore_recognition(self):
        import math
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf,gp_Ax1,gp_Vec
        s,i,j=fixture();tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(1,1,0)),math.pi/3);tr.SetTranslationPart(gp_Vec(1700,2300,-600));s=BRepBuilderAPI_Transform(s,tr,True).Shape()
        _,_,proof=close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=[j],maximum_gap_mm=17)
        self.assertEqual(proof['closed_bores'][0]['radii_mm'],[2.1,3.75])

    def test_invalid_and_outer_wire_selections_reject(self):
        s,i,j=fixture();ff=shape_map(s,TopAbs_FACE);face=TopoDS.Face(ff.FindKey(i));ww=shape_map(face,TopAbs_WIRE);outer=BRepTools.OuterWire_s(face);outer_index=next(k for k in range(1,ww.Extent()+1) if ww.FindKey(k).IsSame(outer))
        for wires in ([],[j,j],[outer_index],[1000]):
            with self.subTest(wires=wires):
                with self.assertRaises(ValueError):close_selected_axial_bores(s,entry_face_index=i,entry_wire_indices=wires,maximum_gap_mm=17)


class LocalRecessTests(unittest.TestCase):
    def fixture(self):
        angle=np.arange(12)*2*np.pi/12;ring=np.column_stack([np.cos(angle),np.sin(angle),np.zeros(12)])
        p=np.concatenate([ring*20,ring*3.75,ring*3.75+[0,0,-3],[[0,0,-3]]]);t=[]
        for i in range(12):
            j=(i+1)%12;t.extend([(i,j,12+j),(i,12+j,12+i),(12+i,12+j,24+j),(12+i,24+j,24+i),(24+i,24+j,36)])
        feature={'axis_direction':[0,0,1],'axis_anchor_mm':[0,0,0],'end_parameters_mm':[-8,0],'radii_mm':[2.1,3.75]}
        return p,np.array(t),np.tile([.2,.2,.2],(len(t),1)),feature

    def test_local_cap_retains_exterior_and_consistent_winding(self):
        p,t,c,f=self.fixture();q,u,d,proof=cap_selected_recess_mesh(p,t,c,[f])
        retained=proof['retained_original_triangle_indices'];np.testing.assert_array_equal(q[u[:len(retained)]],p[t[retained]]);np.testing.assert_array_equal(d[:len(retained)],c[retained])
        self.assertEqual(proof['removed_triangles'],36);self.assertEqual(proof['cap_triangles'],12)
        cap=q[u[len(retained):]];self.assertTrue(np.all(np.cross(cap[:,1]-cap[:,0],cap[:,2]-cap[:,0])[:,2]>0));self.assertTrue(np.all(cap[:,:,2]==0))

    def test_explicit_mouth_cover_preserves_unresolved_interior(self):
        p,t,c,f=self.fixture();f.update(retain_interior=True,mouth_parameter_mm=0)
        q,u,d,proof=cap_selected_recess_mesh(p,t,c,[f])
        np.testing.assert_array_equal(q[u[:len(t)]],p[t]);np.testing.assert_array_equal(d[:len(t)],c)
        self.assertEqual(proof['removed_triangles'],0);self.assertEqual(proof['cap_triangles'],12)

    def test_material_boundary_rejects(self):
        p,t,c,f=self.fixture();c[2]=[1,0,0]
        with self.assertRaises(ValueError):cap_selected_recess_mesh(p,t,c,[f])

    def test_duplicate_and_empty_features_reject(self):
        p,t,c,f=self.fixture()
        for features in ([],[f,f]):
            with self.assertRaises(ValueError):cap_selected_recess_mesh(p,t,c,features)

    def test_disconnected_surfaces_inside_envelope_reject(self):
        p,t,c,f=self.fixture();n=len(p);p=np.concatenate([p,[[0,0,-5],[.3,0,-5],[0,.3,-5],[0,0,-4.7]]]);t=np.concatenate([t,np.array([[0,1,2],[0,3,1],[0,2,3],[1,3,2]])+n]);c=np.concatenate([c,np.tile([.2,.2,.2],(4,1))])
        with self.assertRaises(ValueError):cap_selected_recess_mesh(p,t,c,[f])

    def test_broken_wall_incidence_rejects(self):
        p,t,c,f=self.fixture();t=np.delete(t,2,axis=0);c=np.delete(c,2,axis=0)
        with self.assertRaises(ValueError):cap_selected_recess_mesh(p,t,c,[f])


if __name__=='__main__':unittest.main()
