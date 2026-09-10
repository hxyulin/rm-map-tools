# SPDX-License-Identifier: MIT OR Apache-2.0
"""OCCT regression checks for independent visual/collider meshes."""
import unittest
from unittest.mock import patch
import numpy as np
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from export_policy import ExportPolicy, pair
from mesh_parts import tessellate, tessellate_pair


def cylinder():
    doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    tool.AddShape(BRepPrimAPI_MakeCylinder(100.0, 200.0).Shape(), False)
    return doc


class TessellationTests(unittest.TestCase):
    def test_coarser_request_does_not_reuse_cached_fine_mesh(self):
        doc = cylinder()
        fine = tessellate(doc, 0.1, 0.1)
        coarse = tessellate(doc, 5.0, 0.7)
        fresh = tessellate(cylinder(), 5.0, 0.7)
        self.assertLess(len(coarse[1]), len(fine[1]))
        self.assertEqual(len(coarse[1]), len(fresh[1]))

    def test_pair_keeps_caps_and_respects_chord_error(self):
        settings = {'collision_mode': 'separate', **pair((0.1, 0.1), (5.0, 0.7))}
        fine, coarse = tessellate_pair(cylinder(), settings)
        self.assertLess(len(coarse[1]), len(fine[1]))
        for mesh, bound in [(fine, 0.1), (coarse, 5.0)]:
            p, t, _, _ = mesh
            self.assertAlmostEqual(p[:, 2].min(), 0)
            self.assertAlmostEqual(p[:, 2].max(), 200)
            for triangle in t:
                v = p[triangle]
                if np.ptp(v[:, 2]) < 1e-8:
                    continue
                center = v.mean(axis=0)
                self.assertLessEqual(100 - np.linalg.norm(center[:2]), bound + 1e-6)

    def test_explicit_text_exclusion_keeps_visual_geometry(self):
        settings = ExportPolicy().settings('centre-platform', 'centre-logo-sheets')
        fine, coarse = tessellate_pair(cylinder(), settings)
        self.assertGreater(len(fine[1]), 0)
        self.assertEqual(len(coarse[1]), 0)
        self.assertTrue(ExportPolicy().settings('centre-platform', 'unknown-thin-panel')['collision_enabled'])

    def test_incomplete_coarse_collider_falls_back_to_complete_finer_visual(self):
        complete = tessellate(cylinder(), 1, 0.2)
        settings = {'collision_mode': 'separate', **pair((1, 0.2), (5, 0.7))}
        calls = []
        def mesh(doc, lin, ang, stats):
            calls.append(lin)
            if len(calls) == 2:
                stats['unmeshed_faces'] = 1
            return complete
        stats = {}
        with patch('mesh_parts.tessellate', side_effect=mesh):
            fine, coarse = tessellate_pair(None, settings, stats)
        self.assertIs(fine, coarse)
        self.assertTrue(stats['collision']['fallback_to_visual'])
        self.assertEqual(stats['collision']['effective_tolerance'], settings['visual'])

    def test_failed_finer_collider_cannot_fall_back_to_coarser_visual(self):
        complete = tessellate(cylinder(), 1, 0.2)
        settings = {'collision_mode': 'separate', **pair((5, 0.7), (1, 0.2))}
        def mesh(doc, lin, ang, stats):
            if lin == 1:
                stats['unmeshed_faces'] = 1
            return complete
        with patch('mesh_parts.tessellate', side_effect=mesh), self.assertRaises(ValueError):
            tessellate_pair(None, settings)

    def test_excluded_node_is_a_valid_empty_binding_anchor(self):
        from export_field_package import GlbWriter
        writer = GlbWriter('fixture', {'version': '2.0'})
        writer.add_node('letter', np.zeros((1, 3)), np.empty((0, 3), dtype=int), [])
        self.assertEqual(writer.nodes, [{'name': 'letter'}])
        self.assertEqual(writer.meshes, [])
        writer.add_node('panel', np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]),
                        np.array([[0, 1, 2]]), [None])
        self.assertEqual(writer.nodes[1]['mesh'], 0)
        self.assertEqual(writer.triangles, 1)

    def test_same_geometry_mode_reuses_the_mesh(self):
        fine, coarse = tessellate_pair(cylinder(), ExportPolicy('legacy').settings('base'))
        self.assertIs(fine, coarse)


if __name__ == '__main__':
    unittest.main()
