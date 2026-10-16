# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Layer qualification must respect partial faces and independent motion owners."""
from contextlib import contextmanager
from pathlib import Path
import re
import tempfile
import unittest
from cad_document import CadDocument
from review_cad_layers import review_layers, validate_profile
from test_cad_document import FIXTURE


class LayerReviewTests(unittest.TestCase):
    @contextmanager
    def document(self, extra='', second_body=False, two_faces=False):
        text = FIXTURE
        if second_body:
            text = text.replace("('',(#6),$)", "('',(#6,#26),$)")
            extra += "\n#26=SHELL_BASED_SURFACE_MODEL('',(#27));\n#27=OPEN_SHELL('',(#28));\n#28=ADVANCED_FACE('',(),$,.T.);"
        if two_faces:
            text = text.replace("#7=OPEN_SHELL('',(#8));", "#7=OPEN_SHELL('',(#8,#28));")
            extra += "\n#28=ADVANCED_FACE('',(),$,.T.);"
        text = text.replace('ENDSEC;\nEND-ISO', extra+'\nENDSEC;\nEND-ISO')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.step'
            path.write_text(text)
            with CadDocument.from_step(path, workers=1) as doc:
                yield doc
                self.assertIsNone(doc._working)
                self.assertEqual(path.read_text(), text)

    def profile(self, doc, assignments=()):
        return {'schema_version': 1, 'source_sha256': doc.source_sha256,
                'assignments': [{'product_id': 1, 'body_ids': [body], 'motion': motion, 'motion_owner': str(body),
                                 'evidence': ['fixture reviewed motion']} for body, motion in assignments]}

    def test_unknown_and_partial_selection_do_not_become_fixed_or_decorative(self):
        with self.document(two_faces=True) as doc:
            result = review_layers(doc, self.profile(doc))
            group = result['groups'][0]
            self.assertEqual(group['scope'], 'partial_single_body')
            self.assertEqual(group['body_coverage'][0]['faces_in_layer'], 1)
            self.assertEqual(group['body_coverage'][0]['source_faces'], 2)
            self.assertEqual(group['reviewed_motion_body_counts'], {'unknown': 1})
            self.assertFalse(group['collision_exclusion_qualified'])
            self.assertEqual(group['physical_role'], 'unknown')

    def test_whole_body_reference_and_shared_layer_cannot_merge_motion_owners(self):
        with self.document("#40=PRESENTATION_LAYER_ASSIGNMENT('LED','',(#6,#26));", second_body=True) as doc:
            result = review_layers(doc, self.profile(doc, [(6, 'moving'), (26, 'fixed')]))
            group = result['groups'][-1]
            self.assertEqual(group['scope'], 'multi_body_group')
            self.assertTrue(group['crosses_reviewed_motion_boundary'])
            self.assertTrue(all(b['faces_in_layer'] == 1 for b in group['body_coverage']))
            self.assertFalse(group['light_mask_qualified'])
            self.assertTrue(any('individual light mask' in f for f in group['review_findings']))

    def test_colour_name_with_two_face_colours_is_rejected(self):
        styles = FIXTURE[FIXTURE.index('#12='):FIXTURE.index('#20=')]
        styles = re.sub(r'#(\d+)', lambda m: '#'+str(28 if int(m[1]) == 8 else int(m[1])+50), styles)
        styles = styles.replace('0.123456789,0.2,0.3', '1.,0.,0.')
        with self.document(styles+"#80=PRESENTATION_LAYER_ASSIGNMENT('COLOR1','',(#6));", two_faces=True) as doc:
            group = review_layers(doc, self.profile(doc))['groups'][-1]
            self.assertEqual(group['scope'], 'complete_single_body')
            self.assertEqual(len(group['effective_face_rgb_4dp_counts']), 2)
            self.assertTrue(any('single-colour mask' in f for f in group['review_findings']))
            self.assertFalse(group['collision_exclusion_qualified'])

    def test_stale_conflicting_and_wrong_owner_profiles_fail(self):
        with self.document() as doc:
            wrong = self.profile(doc)
            wrong['source_sha256'] = 'different'
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                validate_profile(doc, wrong)
            for assignments in ([(6, 'moving'), (6, 'fixed')], [(999, 'fixed')]):
                with self.assertRaisesRegex(ValueError, 'duplicate assignment|not owned'):
                    validate_profile(doc, self.profile(doc, assignments))
            no_evidence = self.profile(doc, [(6, 'fixed')])
            no_evidence['assignments'][0]['evidence'] = []
            with self.assertRaisesRegex(ValueError, 'evidence'):
                validate_profile(doc, no_evidence)


if __name__ == '__main__':
    unittest.main()
