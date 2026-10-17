# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Profile colliders must preserve sockets, recesses and large panel windows."""
import math
import unittest
import numpy as np
from cad_collision_profiles import simplify_loop, native_loops, prism_mesh, revolve_profile, meridian_section
from mesh_quality import distances
from cad_wall_fill import shape_map
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir


class CollisionProfilesTests(unittest.TestCase):
    def test_prism_window_is_not_filled(self):
        outer = {'outer': True, 'points_mm': np.array([[0., 0, 0], [40, 0, 0], [40, 40, 0], [0, 40, 0]])}
        inner = {'outer': False, 'points_mm': np.array([[10., 10, 0], [30, 10, 0], [30, 30, 0], [10, 30, 0]])}
        p, t, proof = prism_mesh([outer, inner], [0, 0, 1], 3)
        self.assertTrue(proof['closed_oriented_manifold']); self.assertAlmostEqual(proof['signed_volume_mm3'], 3600)
        self.assertAlmostEqual(distances(np.array([[20., 20, -1.5]]), p, t)[0], 10)

    def test_revolution_preserves_blind_socket_and_axis_winding(self):
        loop = [{'outer': True, 'points_ry_mm': np.array([[6., 0], [10, 0], [10, 100], [0, 100], [0, 80], [6, 80]])}]
        for axis in [0, 1, 2]:
            p, t, proof = revolve_profile(loop, angular_segments=32, axis=axis)
            self.assertTrue(proof['closed_oriented_manifold']); self.assertGreater(proof['signed_volume_mm3'], 0)
            a = np.zeros(3); a[axis] = 40
            self.assertGreater(distances(a[None], p, t)[0], 5.9)
            a[axis] = 80; self.assertLess(distances(a[None], p, t)[0], 1e-8)
            expected = math.pi * (100 * 100 - 36 * 80)
            self.assertLess(abs(proof['signed_volume_mm3'] / expected - 1), .01)

    def test_native_section_keeps_annular_recess(self):
        def cylinder(r, start, length): return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, start, 0), gp_Dir(0, 1, 0)), r, length).Shape()
        source = BRepAlgoAPI_Fuse(cylinder(20, 0, 20), cylinder(10, 20, 80)).Shape()
        source = BRepAlgoAPI_Cut(source, cylinder(6, -1, 81)).Shape()
        ring = BRepAlgoAPI_Cut(cylinder(17, 5, 16), cylinder(12, 4, 18)).Shape()
        source = BRepAlgoAPI_Cut(source, ring).Shape()
        loops, proof = meridian_section(source, angle_rad=.29, radius_limit_mm=25, height_range_mm=(-1, 101), boundary_error_mm=.05)
        p, t, topology = revolve_profile(loops, angular_segments=32)
        self.assertEqual(proof['section_faces'], 1); self.assertTrue(topology['closed_oriented_manifold'])
        # Source-owned groove has walls at radius 12 and 17, not the outer 20.
        self.assertGreater(distances(np.array([[14., 10, 0]]), p, t)[0], 1.8)
        self.assertLess(distances(np.array([[17., 10, 0]]), p, t)[0], .1)
        self.assertLess(abs(topology['signed_volume_mm3'] / (math.pi * 10945) - 1), .01)

    def test_only_strictly_small_native_holes_close(self):
        source = BRepPrimAPI_MakeBox(100, 60, 3).Shape()
        for x, radius in [(20, 5), (65, 10)]:
            hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, 30, -1), gp_Dir(0, 0, 1)), radius, 5).Shape(); source = BRepAlgoAPI_Cut(source, hole).Shape()
        faces = shape_map(source, TopAbs_FACE)
        front = next(TopoDS.Face(faces.FindKey(i)) for i in range(1, faces.Extent() + 1) if BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(i))).GetType() == GeomAbs_Plane and abs(BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(i))).Plane().Location().Z() - 3) < 1e-8)
        loops, proof = native_loops(front, close_holes_below_mm=17)
        self.assertEqual(len(loops), 2); self.assertEqual(sum(r['operation'] == 'close-small-hole' for r in proof['wires']), 1)
        p, t, _ = prism_mesh(loops, [0, 0, 1], 3)
        self.assertGreater(distances(np.array([[65., 30, 1.5]]), p, t)[0], 9)

    def test_invalid_policies_reject(self):
        with self.assertRaises(ValueError): simplify_loop([[0, 0], [1, 0]], 1)
        with self.assertRaises(ValueError): prism_mesh([], [0, 0, 1], 3)
        with self.assertRaises(ValueError): revolve_profile([], angular_segments=2)
        with self.assertRaises(ValueError): native_loops(BRepPrimAPI_MakeBox(1, 1, 1).Shape(), close_holes_below_mm=-1)
