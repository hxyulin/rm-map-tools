# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Semantic audits distinguish source evidence from speculative runtime roles."""
from pathlib import Path
import tempfile
import unittest
from cad_document import CadDocument
from audit_cad_passes import run_document
from audit_semantic_evidence import hints
from test_cad_document import FIXTURE


class SemanticEvidenceTests(unittest.TestCase):
    def audit(self, extra=''):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.step'
            path.write_text(FIXTURE.replace('ENDSEC;\nEND-ISO', extra+'\nENDSEC;\nEND-ISO'))
            with CadDocument.from_step(path, workers=1) as doc:
                result = run_document(doc, ['semantic-evidence'])
                self.assertIsNone(doc._working)
                self.assertEqual(list(Path(tmp).iterdir()), [path])
                self.assertTrue(result['source_unchanged'])
                return result['passes'][0]['findings']

    def test_paint_name_and_no_kinematics_never_assign_roles(self):
        result = self.audit()
        summary = result['summary']
        self.assertEqual(summary['explicit_motion_records'], 0)
        self.assertEqual(summary['confirmed_static_bodies'], 0)
        self.assertEqual(summary['confirmed_decoration_bodies'], 0)
        group = result['layer_memberships'][0]
        self.assertEqual(group['referenced_body_ids'], [6])
        self.assertEqual(group['referenced_owner_product_ids'], [1])
        self.assertEqual(group['physical_role'], 'unknown')
        self.assertFalse(group['all_targets_are_appearance_records'])
        self.assertEqual(result['appearance_evidence']['style_target_types'], {'ADVANCED_FACE': 1})

    def test_identical_lists_keep_both_names_but_do_not_conflate_different_lists(self):
        result = self.audit("""
#21=PRESENTATION_LAYER_ASSIGNMENT('LED','',(#8));
#22=PRESENTATION_LAYER_ASSIGNMENT('COLOR1','',(#19));
#23=PRESENTATION_LAYER_ASSIGNMENT('other','',(#6));
""")
        self.assertEqual(result['summary']['layers'], 4)
        self.assertEqual(result['summary']['unique_ordered_memberships'], 3)
        a, b, c = result['layer_memberships']
        self.assertEqual([n['name'] for n in a['layers']], ['paint', 'LED'])
        self.assertTrue(b['all_targets_are_appearance_records'])
        self.assertEqual(b['physical_role'], 'unknown')
        self.assertFalse(c['all_targets_are_appearance_records'])
        self.assertEqual(result['summary']['faces_in_multiple_layers'], 1)

    def test_complex_kinematic_types_are_evidence_without_automatic_body_binding(self):
        result = self.audit("""
#21=MECHANICAL_CONTEXT('KINEMATIC_JOINT( fake',#1,'');
#22=SURFACE_OF_REVOLUTION('',#1,#1);
#23=(REPRESENTATION_ITEM('') KINEMATIC_PAIR('test',#6));
""")
        self.assertEqual(result['motion_evidence'], [{'source_id': 23, 'types': ['KINEMATIC_PAIR']}])
        self.assertEqual(result['summary']['confirmed_dynamic_bodies'], 0)

    def test_colour_hint_accepts_empty_description_whitespace(self):
        self.assertEqual(hints('COLOR61_2 '), ['colour'])
        self.assertIn('decoration', hints('地面带丝印'))


if __name__ == '__main__':
    unittest.main()
