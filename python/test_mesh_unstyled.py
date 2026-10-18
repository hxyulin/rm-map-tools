# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Skipping empty-table color resolution preserves geometry and authored paint."""
import unittest
from unittest.mock import patch

import numpy as np
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorGen
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
from mesh_parts import tessellate, _has_colours
from validate_parts import analyse


class UnstyledMeshTests(unittest.TestCase):
    def document(self):
        doc = TDocStd_Document(TCollection_ExtendedString('XmlXCAF'))
        shape = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
        label = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).AddShape(shape, False)
        return doc, label

    def test_empty_color_table_has_identical_mesh_and_fallback_palette(self):
        doc, _ = self.document()
        colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
        self.assertFalse(_has_colours(colors))
        # Force the original resolution path as the reference, without inventing
        # paint or modifying the document/shape between the two tessellations.
        with patch('mesh_parts._has_colours', return_value=True):
            expected = tessellate(doc, .5, .5)
        with patch('mesh_parts._instance_face_colours', side_effect=AssertionError('empty color table')):
            actual = tessellate(doc, .5, .5)
        for left, right in zip(actual[:3], expected[:3]):
            np.testing.assert_array_equal(left, right)
        self.assertEqual(actual[3], expected[3])
        self.assertEqual(actual[3], [None])
        with patch('validate_parts.has_source_colours', return_value=True):
            expected_stats = analyse(doc)
        self.assertEqual(analyse(doc), expected_stats)
        self.assertEqual(expected_stats['face_colours'], {'None': 6})

    def test_body_paint_keeps_original_resolution(self):
        doc, label = self.document()
        colors = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
        colors.SetColor(label, Quantity_Color(.2, .4, .6, Quantity_TOC_RGB), XCAFDoc_ColorGen)
        self.assertTrue(_has_colours(colors))
        _, triangles, indices, palette = tessellate(doc, .5, .5)
        self.assertEqual(len(triangles), 12)
        self.assertEqual(len(palette), 1)
        self.assertIsNotNone(palette[0])
        self.assertTrue(np.all(indices == 0))


if __name__ == '__main__':
    unittest.main()
