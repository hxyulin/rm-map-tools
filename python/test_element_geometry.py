# SPDX-License-Identifier: MIT OR Apache-2.0
"""OCP-venv regression tests for sheet preservation and element origins."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from export_elements import footprint_origin
from mesh_parts import analytic_band
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.gp import gp_Ax3, gp_Cone
from p21index import Index, build_index
from p21model import Model
from p21split import Splitter


class ElementGeometryTests(unittest.TestCase):
    def test_body_selection_keeps_sheet_geometry_and_its_style(self):
        source = """ISO-10303-21;
HEADER;
ENDSEC;
DATA;
#1=PRODUCT('mixed','mixed','',(#2));
#2=APPLICATION_CONTEXT('');
#3=PRODUCT_DEFINITION_FORMATION('','',#1);
#4=PRODUCT_DEFINITION('','',#3,#2);
#5=PRODUCT_DEFINITION_SHAPE('','',#4);
#6=SHAPE_DEFINITION_REPRESENTATION(#5,#7);
#7=SHAPE_REPRESENTATION('',(#8,#10),#2);
#8=MANIFOLD_SOLID_BREP('',#9);
#9=CLOSED_SHELL('',());
#10=SHELL_BASED_SURFACE_MODEL('',(#11));
#11=OPEN_SHELL('',(#12));
#12=ADVANCED_FACE('',(),#13,.T.);
#13=PLANE('',#14);
#14=CARTESIAN_POINT('',(0.,0.,0.));
#15=STYLED_ITEM('',(#16),#12);
#16=PRESENTATION_STYLE_ASSIGNMENT(());
ENDSEC;
END-ISO-10303-21;
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'source.step'
            path.write_text(source)
            np.savez(root / 'source.npz', **build_index(str(path), workers=1))
            ix = Index(root / 'source.npz')
            try:
                splitter = Splitter(ix, Model(ix))
                mask, rewritten = splitter.closure_products([ix.r(1)], body_ids={10})
                for eid in (10, 11, 12, 13, 14, 15, 16):
                    self.assertTrue(mask[ix.r(eid)], eid)
                for eid in (8, 9):
                    self.assertFalse(mask[ix.r(eid)], eid)
                self.assertNotIn(b'#8', rewritten[ix.r(7)])
                self.assertIn(b'#10', rewritten[ix.r(7)])
                all_bodies, _ = splitter.closure_products([ix.r(1)])
                self.assertTrue(all_bodies[ix.r(8)] and all_bodies[ix.r(10)])
            finally:
                ix.mm.close()
                ix._f.close()

    def test_origin_uses_visual_extrema_and_preserves_placement(self):
        points = np.array([[-0.36, -0.38, 0.03], [0.42, 0.27, 0.81], [0.1, 0.0, 0.0]])
        origin = footprint_origin(points)
        local = points - origin
        np.testing.assert_allclose((local.min(0) + local.max(0))[:2], 0, atol=1e-12)
        self.assertEqual(local[:, 2].min(), 0)
        np.testing.assert_allclose(local + origin, points, atol=1e-12)

    def test_analytic_fallback_preserves_complete_bands_and_refuses_trimmed_spans(self):
        cone = gp_Cone(gp_Ax3(), 0.035, 1.0)
        face = BRepBuilderAPI_MakeFace(cone, -np.pi, np.pi, -1.35, 0.15).Face()
        mesh = analytic_band(face, 2.0, 0.35)
        self.assertIsNotNone(mesh)
        for i in range(1, mesh.NbNodes() + 1):
            point = mesh.Node(i)
            expected_radius = 1.0 + point.Z() * np.tan(0.035)
            self.assertAlmostEqual(np.hypot(point.X(), point.Y()), expected_radius, places=9)
        trimmed = BRepBuilderAPI_MakeFace(cone, 0.0, np.pi, -1.35, 0.15).Face()
        self.assertIsNone(analytic_band(trimmed, 2.0, 0.35))

    def test_mixed_centre_product_is_partitioned_without_overlap(self):
        rules = json.loads((Path(__file__).parent.parent / 'rules/elements-v1.2.0.json').read_text())
        groups = {}
        for element in rules['elements']:
            groups.update(element.get('body_groups', {}))
        sets = {name: {i for lo, hi in spec['body_id_ranges'] for i in range(lo, hi + 1)}
                for name, spec in groups.items()}
        self.assertEqual(len(sets['centre-logo-sheets']), 62)
        self.assertEqual(len(sets['tech-core-positive-details']), 1681)
        self.assertEqual(len(sets['tech-core-negative-details']), 1681)
        union = set().union(*sets.values())
        self.assertEqual(len(union), sum(map(len, sets.values())))
        self.assertEqual(len(union), 3424)
        fortress = next(e for e in rules['elements'] if e['name'] == 'fortress')
        self.assertTrue(all(len(instance) == 5 for instance in fortress['instances']))


if __name__ == '__main__':
    unittest.main()
