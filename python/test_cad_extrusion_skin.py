# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verify shared cap boundaries and rejection instead of guessing extrusion LOD."""
import unittest
import numpy as np
from cad_extrusion_skin import extrusion_skin
from cad_wall_fill import shape_map
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.Geom import Geom_BezierCurve
from OCP.GeomConvert import GeomConvert
from OCP.collections import Array1_gp_Pnt
from OCP.gp import gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_SurfaceOfExtrusion


def fixture(hole=False):
    controls = Array1_gp_Pnt(1, 3)
    for i, p in enumerate(((0, 10, 0), (50, 40, 0), (100, 10, 0)), 1): controls.SetValue(i, gp_Pnt(*p))
    curve = GeomConvert.CurveToBSplineCurve_s(Geom_BezierCurve(controls))
    wire = BRepBuilderAPI_MakeWire(); wire.Add(BRepBuilderAPI_MakeEdge(curve).Edge())
    for a, b in [((100, 10, 0), (100, 0, 0)), ((100, 0, 0), (0, 0, 0)), ((0, 0, 0), (0, 10, 0))]: wire.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*a), gp_Pnt(*b)).Edge())
    solid = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(wire.Wire()).Face(), gp_Vec(0, 0, 50)).Shape()
    if hole:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        solid = BRepAlgoAPI_Cut(solid, BRepPrimAPI_MakeBox(gp_Pnt(45, 3, -1), 10, 4, 52).Shape()).Shape()
    faces = shape_map(solid, TopAbs_FACE)
    selected = [i for i in range(1, faces.Extent() + 1) if BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(i))).GetType() == GeomAbs_SurfaceOfExtrusion]
    return solid, faces, selected


class ExtrusionSkinTests(unittest.TestCase):
    def test_caps_share_the_actual_profile_vertices(self):
        _, faces, selected = fixture()
        changed, proof = extrusion_skin(faces, selected, sections=16, maximum_profile_error_mm=.1, sample_count=4097)
        self.assertEqual(len(changed), 3)
        self.assertEqual(len(proof['neighbor_caps']), 2)
        p, t = changed[selected[0]]
        for cap in proof['neighbor_caps']:
            q, f = changed[cap['native_face_index']]
            # Each cap contains one complete side of the extrusion strip.
            self.assertGreaterEqual(len(set(map(tuple, p)) & set(map(tuple, q))), 17)
        # Every non-end profile edge has one strip use and one cap use.
        all_points = np.concatenate([q for q, f in changed.values()]); offset = 0; triangles = []
        for q, f in changed.values(): triangles.append(f + offset); offset += len(q)
        points, inverse = np.unique(all_points, axis=0, return_inverse=True); triangles = inverse[np.concatenate(triangles)]
        ee = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
        _, counts = np.unique(ee, axis=0, return_counts=True)
        self.assertLessEqual(counts.max(), 2)
        self.assertEqual(int((counts == 1).sum()), 8)  # Six cap edges plus the strip's two end edges.
        self.assertLess(max(r['maximum_sampled_profile_error_mm'] for r in proof['edge_profiles']), .1)

    def test_rejects_error_and_wrong_source_faces(self):
        _, faces, selected = fixture()
        with self.assertRaisesRegex(ValueError, 'allowance'): extrusion_skin(faces, selected, sections=2, maximum_profile_error_mm=.01)
        with self.assertRaises(ValueError): extrusion_skin(faces, [0], sections=16)
        planar = next(i for i in range(1, faces.Extent() + 1) if i not in selected)
        with self.assertRaises(ValueError): extrusion_skin(faces, [planar], sections=16)

    def test_cap_holes_are_not_filled(self):
        from mesh_quality import distances
        _, faces, selected = fixture(hole=True)
        changed, proof = extrusion_skin(faces, selected, sections=16, maximum_profile_error_mm=.1, sample_count=4097)
        self.assertTrue(all(c['loops'] == 2 for c in proof['neighbor_caps']))
        for cap in proof['neighbor_caps']:
            p, t = changed[cap['native_face_index']]
            self.assertGreater(distances(np.array([[50., 5, 0], [50, 5, 50]]), p, t).min(), 1.99)
