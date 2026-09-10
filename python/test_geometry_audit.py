# SPDX-License-Identifier: MIT OR Apache-2.0
import math
import unittest

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Pnt

from audit_geometry import inspect_topology, summarize
from mesh_parts import tessellate


def document(*shapes):
    doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    for shape in shapes:
        tool.AddShape(shape, False)
    return doc


class GeometryAuditTests(unittest.TestCase):
    def test_hole_candidates_distinguish_external_cylinder_and_perforated_plate(self):
        plate = BRepPrimAPI_MakeBox(100, 100, 10).Shape()
        hole = BRepPrimAPI_MakeCylinder(3, 10).Shape()
        # Keep hole away from the outer boundary.
        from OCP.gp import gp_Trsf, gp_Vec
        from OCP.TopLoc import TopLoc_Location
        move = gp_Trsf()
        move.SetTranslation(gp_Vec(50, 50, 0))
        plate = BRepAlgoAPI_Cut(plate, hole.Moved(TopLoc_Location(move))).Shape()
        doc = document(plate, BRepPrimAPI_MakeCylinder(2, 20).Shape())
        records, bodies = inspect_topology(doc)
        counts = {}
        mesh = tessellate(doc, 1, 0.5, face_observer=lambda i, f, n: counts.__setitem__(i, n))
        result = summarize(records, bodies, counts, 30, 5)
        self.assertEqual(result['triangles'], len(mesh[1]))
        self.assertEqual(result['hole_candidates']['faces'], 1)
        self.assertEqual(result['perforated_planes']['faces'], 2)
        self.assertEqual(result['perforated_planes']['small_circular_openings'], 2)
        self.assertEqual(result['small_bodies']['count'], 1)
        self.assertGreater(result['hole_candidates']['wall_triangles'], 0)

    def test_full_half_and_trimmed_spheres_are_distinct(self):
        for shape, expected in [
            (BRepPrimAPI_MakeSphere(10).Shape(), 'full'),
            (BRepPrimAPI_MakeSphere(10, 0, math.pi / 2).Shape(), 'hemisphere'),
            (BRepPrimAPI_MakeSphere(10, -0.2, 0.2).Shape(), 'trimmed'),
        ]:
            faces, _ = inspect_topology(document(shape))
            sphere = next(f for f in faces.values() if f['surface'] == 'Sphere')
            self.assertEqual(sphere['sphere_patch'], expected)

    def test_audit_counts_include_sheet_faces_without_solid_owners(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Pln, gp_Dir
        sheet = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(), gp_Dir(0, 0, 1)), 0, 20, 0, 20).Face()
        doc = document(sheet)
        faces, bodies = inspect_topology(doc)
        counts = {}
        tessellate(doc, 1, 0.5, face_observer=lambda i, f, n: counts.__setitem__(i, n))
        self.assertEqual(len(bodies), 0)
        self.assertEqual(summarize(faces, bodies, counts, 30, 5)['triangles'], 2)

    def test_relaxed_spheres_keep_linear_error_and_all_faces(self):
        import numpy as np
        for radius in (3, 100):
            doc = document(BRepPrimAPI_MakeSphere(radius).Shape())
            fine = tessellate(doc, 1, 0.5)
            stats = {}
            coarse = tessellate(doc, 1, 0.9, stats)
            self.assertLessEqual(len(coarse[1]), len(fine[1]))
            if radius == 3:
                self.assertLess(len(coarse[1]), len(fine[1]))
            self.assertFalse(stats.get('unmeshed_faces'))
            centers = coarse[0][coarse[1]].mean(axis=1)
            self.assertLessEqual(float(np.max(radius - np.linalg.norm(centers, axis=1))), 1 + 1e-6)


if __name__ == '__main__':
    unittest.main()
