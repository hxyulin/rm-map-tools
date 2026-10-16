# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Sharing changes references only: source topology, appearance and occurrences survive."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import numpy as np
from cad_document import CadDocument
from cad_passes import CadScene, plan_pass, apply_plan, face_correspondence, validate_equivalence

FIXTURE = """ISO-10303-21;
HEADER;
ENDSEC;
DATA;
#1=PRODUCT('root','root','',(#4));
#2=PRODUCT_DEFINITION_FORMATION('','',#1);
#3=PRODUCT_DEFINITION('','',#2,$);
#4=PRODUCT_CONTEXT('','part definition',$);
#5=PRODUCT_DEFINITION_SHAPE('','',#3);
#6=SHELL_BASED_SURFACE_MODEL('first',(#7));
#7=OPEN_SHELL('',(#8));
#8=ADVANCED_FACE('',(),$,.T.);
#9=SHAPE_DEFINITION_REPRESENTATION(#5,#10);
#10=MANIFOLD_SURFACE_SHAPE_REPRESENTATION('',(#6,#106,#206),$);
#106=SHELL_BASED_SURFACE_MODEL('copy',(#107));
#107=OPEN_SHELL('',(#108));
#108=ADVANCED_FACE('',(),$,.T.);
#206=SHELL_BASED_SURFACE_MODEL('changed',(#207));
#207=OPEN_SHELL('',(#208));
#208=ADVANCED_FACE('',(),$,.F.);
#12=COLOUR_RGB('red',1.,0.,0.);
#13=FILL_AREA_STYLE_COLOUR('',#12);
#14=FILL_AREA_STYLE('',(#13));
#15=SURFACE_STYLE_FILL_AREA(#14);
#16=SURFACE_SIDE_STYLE('',(#15));
#17=SURFACE_STYLE_USAGE(.POSITIVE.,#16);
#18=PRESENTATION_STYLE_ASSIGNMENT((#17));
#19=STYLED_ITEM('',(#18),#8);
#112=COLOUR_RGB('red',1.,0.,0.);
#113=FILL_AREA_STYLE_COLOUR('',#112);
#114=FILL_AREA_STYLE('',(#113));
#115=SURFACE_STYLE_FILL_AREA(#114);
#116=SURFACE_SIDE_STYLE('',(#115));
#117=SURFACE_STYLE_USAGE(.POSITIVE.,#116);
#118=PRESENTATION_STYLE_ASSIGNMENT((#117));
#119=STYLED_ITEM('',(#118),#108);
#212=COLOUR_RGB('blue',0.,0.,1.);
#213=FILL_AREA_STYLE_COLOUR('',#212);
#214=FILL_AREA_STYLE('',(#213));
#215=SURFACE_STYLE_FILL_AREA(#214);
#216=SURFACE_SIDE_STYLE('',(#215));
#217=SURFACE_STYLE_USAGE(.NEGATIVE.,#216);
#218=PRESENTATION_STYLE_ASSIGNMENT((#217));
#219=STYLED_ITEM('',(#218),#106);
#312=COLOUR_RGB('different semantic name',1.,0.,0.);
#313=FILL_AREA_STYLE_COLOUR('',#312);
#314=FILL_AREA_STYLE('',(#313));
#315=SURFACE_STYLE_FILL_AREA(#314);
#316=SURFACE_SIDE_STYLE('',(#315));
#317=SURFACE_STYLE_USAGE(.POSITIVE.,#316);
#318=PRESENTATION_STYLE_ASSIGNMENT((#317));
#319=STYLED_ITEM('',(#318),#208);
ENDSEC;
END-ISO-10303-21;
"""


class SharingPassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)/'scene.step'
        path.write_text(FIXTURE)
        self.doc = CadDocument.from_step(path)
        # This fixture is a single root with no assembly edges.
        self.doc._transforms = {}
        self.scene = CadScene(self.doc)

    def tearDown(self):
        self.doc.close()
        self.temp.cleanup()

    def test_geometry_is_shared_but_face_and_body_styles_keep_their_owners(self):
        before = list(self.scene.occurrences())
        plan = plan_pass(self.scene, 'share-exact-geometry')
        self.assertEqual([(r.source_id, r.canonical_id) for r in plan.redirects], [(106, 6)])
        self.assertEqual(self.scene.geometry(106), 106)  # Planning does not apply.
        result = apply_plan(self.scene, plan)
        self.assertEqual(result.geometry(106), 6)
        self.assertEqual(result.geometry(206), 206)  # Changed face orientation is retained.
        self.assertEqual(result.geometry_face(106, 108), 8)
        self.assertEqual(self.doc.styles(108)[0].id, 119)
        self.assertEqual(self.doc.styles(106)[0].id, 219)
        after = list(result.occurrences())
        self.assertEqual(len(before), len(after))
        for a, b in zip(before, after):
            self.assertEqual(a.source_body_id, b.source_body_id)
            self.assertEqual(a.occurrence_path, b.occurrence_path)
            np.testing.assert_array_equal(a.matrix, b.matrix)
        self.assertEqual(len(plan_pass(result, plan.pass_id).redirects), 0)
        self.doc.verify_source()

    def test_appearance_shares_only_exact_graphs_and_preserves_names_sides_and_bindings(self):
        plan = plan_pass(self.scene, 'share-exact-appearance')
        self.assertEqual([(r.source_id, r.canonical_id) for r in plan.redirects], [(118, 18)])
        result = apply_plan(self.scene, plan)
        self.assertEqual(result.appearance(118), 18)
        self.assertEqual(result.appearance(218), 218)
        self.assertEqual(result.appearance(318), 318)
        self.assertEqual([(s, target) for s, target, _ in result.style_bindings()],
                         [(19, 8), (119, 108), (219, 106), (319, 208)])
        self.assertEqual(next(r for r in result.style_bindings() if r[0] == 119)[2], (18,))
        self.assertEqual(self.scene.appearance(118), 118)
        self.assertEqual(len(plan_pass(result, plan.pass_id).redirects), 0)

    def test_stale_wrong_source_and_forged_evidence_are_rejected_atomically(self):
        plan = plan_pass(self.scene, 'share-exact-geometry')
        for bad in (replace(plan, revision=9), replace(plan, source_sha256='other'),
                    replace(plan, redirects=(replace(plan.redirects[0], graph_sha256='forged'),)),
                    replace(plan, redirects=(replace(plan.redirects[0], face_pairs=()),))):
            with self.assertRaises(ValueError):
                apply_plan(self.scene, bad)
            self.assertEqual(dict(self.scene.geometry_aliases), {})
        with self.assertRaises(TypeError):
            self.scene.geometry_aliases[106] = 6

    def test_passes_compose_and_reject_unknown_passes(self):
        result = self.scene
        for name in ('share-exact-geometry', 'share-exact-appearance'):
            result = apply_plan(result, plan_pass(result, name))
        self.assertEqual(result.geometry(106), 6)
        self.assertEqual(result.appearance(118), 18)
        self.assertEqual(result.statistics()['shared_geometry_definitions'], 2)
        self.assertEqual(result.statistics()['shared_appearance_definitions'], 3)
        validation = validate_equivalence(self.scene, result)
        self.assertEqual(validation['body_occurrences_preserved'], 3)
        self.assertEqual(validation['style_bindings_preserved'], 4)
        wrong = CadScene(self.doc, geometry_aliases={206: 6})
        with self.assertRaisesRegex(ValueError, 'geometry changed'):
            validate_equivalence(self.scene, wrong)
        wrong = CadScene(self.doc, appearance_aliases={218: 18})
        with self.assertRaisesRegex(ValueError, 'style graph changed'):
            validate_equivalence(self.scene, wrong)
        with self.assertRaises(ValueError):
            plan_pass(result, 'fill-holes')
        no_op = plan_pass(result, 'share-exact-geometry')
        self.assertIs(apply_plan(result, no_op), result)

    def test_face_mapping_is_scoped_to_body_not_global_source_face_id(self):
        result = apply_plan(self.scene, plan_pass(self.scene, 'share-exact-geometry'))
        self.assertEqual(result.geometry_face(106, 108), 8)
        # A shared source face may also be used in a retained, different body.
        # That body's face identity must not follow another body's redirect.
        self.assertEqual(result.geometry_face(206, 108), 108)

    def test_nonbijective_shared_face_graph_is_refused(self):
        # Matching unfolded graphs can have different internal sharing. Reusing
        # one face twice cannot stand in for two independently styled source faces.
        records = {1: ('SHELL_BASED_SURFACE_MODEL', [2]), 2: ('OPEN_SHELL', [3, 3]),
                   3: ('ADVANCED_FACE', []), 4: ('SHELL_BASED_SURFACE_MODEL', [5]),
                   5: ('OPEN_SHELL', [6, 7]), 6: ('ADVANCED_FACE', []), 7: ('ADVANCED_FACE', [])}
        from types import SimpleNamespace
        ix = SimpleNamespace(tname=lambda r: records[r][0], refs_of=lambda r: records[r][1],
                             r=lambda r: r, ids=np.arange(10))
        model = SimpleNamespace(body_faces=lambda r: [3] if r == 1 else [6, 7])
        with self.assertRaisesRegex(ValueError, 'bijective'):
            face_correspondence(SimpleNamespace(index=ix, model=model), 1, 4)


if __name__ == '__main__':
    unittest.main()
