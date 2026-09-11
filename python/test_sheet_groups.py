"""Checks for group selection and assembly-aware geometry/colour verification."""
import unittest
import numpy as np
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.gp import gp_Pln, gp_Pnt, gp_Dir, gp_Trsf, gp_Vec
from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorSurf
from prototype_sheet_groups import select_orbits, face_records, compare_documents


def fixture(shared, changed_colour=False):
    doc=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    st=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main());ct=XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    root=st.NewShape() if shared else None
    faces=[BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0,0,z),gp_Dir(0,0,1)),0,1,0,2).Face() for z in [0,1]]
    colours=[Quantity_Color(1,0,0,Quantity_TOC_sRGB),Quantity_Color(0,0,1,Quantity_TOC_sRGB)]
    if changed_colour:colours[1]=colours[0]
    for face,col in zip(faces,colours):
        definition=st.AddShape(face,False) if shared else None
        if shared:ct.SetColor(definition,col,XCAFDoc_ColorSurf)
        for offset in [0,4]:
            transform=gp_Trsf();transform.SetTranslation(gp_Vec(offset,0,0))
            if shared:
                st.AddComponent(root,definition,TopLoc_Location(transform))
            else:
                shape=BRepBuilderAPI_Transform(face,transform,True).Shape()
                label=st.AddShape(shape,False);ct.SetColor(label,col,XCAFDoc_ColorSurf)
    st.UpdateAssemblies()
    return doc


class SheetGroupTests(unittest.TestCase):
    def test_selects_disjoint_body_orbits_and_ignores_wrong_product(self):
        identity=np.eye(4);placement=np.eye(4);placement[0,3]=5
        def body(eid,m,product='part'):
            return dict(id=eid,products=[product],reference_to_body_matrix_mm=m.tolist())
        groups=[dict(type='SHELL_BASED_SURFACE_MODEL',representative_geometry_entities=20,
                     bodies=[body(1,identity),body(2,placement)]),
                dict(type='SHELL_BASED_SURFACE_MODEL',representative_geometry_entities=10,
                     bodies=[body(3,identity),body(4,placement)]),
                dict(type='SHELL_BASED_SURFACE_MODEL',representative_geometry_entities=10,
                     bodies=[body(5,identity,'other'),body(6,placement,'other')])]
        matrices,orbits=select_orbits(groups,'part')
        self.assertEqual([item['instance_bodies'] for item in orbits],[[1,2],[3,4]])
        np.testing.assert_array_equal(matrices[0],identity)

    def test_rejects_mirrored_seed_transform(self):
        mirror=np.eye(4);mirror[0,0]=-1
        group=dict(type='SHELL_BASED_SURFACE_MODEL',bodies=[dict(id=1,products=['part'],reference_to_body_matrix_mm=mirror.tolist())])
        with self.assertRaises(ValueError):select_orbits([group],'part')

    def test_shared_definition_colours_and_geometry_survive_placements(self):
        before=fixture(False);after=fixture(True)
        records,storage=face_records(after)
        self.assertEqual(storage['stored_faces'],2);self.assertEqual(len(records),4)
        result=compare_documents(before,after)
        self.assertTrue(result['per_face_colours_match'])
        self.assertEqual(result['boolean_face_pairs_checked'],4)
        self.assertEqual(result['max_bidirectional_cut_area_mm2'],0)

    def test_imported_colour_change_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_documents(fixture(False),fixture(True,changed_colour=True))

if __name__=='__main__':unittest.main()
