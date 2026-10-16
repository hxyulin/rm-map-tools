# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Component grouping retains complete coverage, source identity and placements."""
import copy
from pathlib import Path
import tempfile
import unittest
from cad_document import CadDocument
from cad_components import build_catalog, select_components, export_selection
import test_review_cad_layers as layer_fixture


class ComponentTests(unittest.TestCase):
    def inputs(self, doc):
        policy = {'schema_version': 1, 'source_sha256': doc.source_sha256,
                  'product_names': {'1': 'fixture'}, 'groups': []}
        motion = {'schema_version': 1, 'source_sha256': doc.source_sha256, 'assignments': []}
        return policy, motion

    def test_every_body_has_one_leaf_and_manual_remainder_is_preserved(self):
        with layer_fixture.LayerReviewTests().document(second_body=True) as doc:
            policy, motion = self.inputs(doc)
            policy['groups'] = [{'product_id': 1, 'path': ['module'], 'body_ids': [6], 'evidence': ['fixture']}]
            result = build_catalog(doc, policy, motion)
            self.assertEqual(result['summary']['component_definitions'], 2)
            self.assertEqual(result['summary']['placed_component_occurrences'], 2)
            self.assertEqual([c['body_id'] for c in result['components']], [6, 26])
            self.assertEqual([c['group'] for c in result['components']], ['fixture/module', 'fixture/other-bodies'])
            selected = select_components(result, 'fixture/module')
            self.assertEqual([c['id'] for c in selected['components']], ['p1.b6'])
            self.assertEqual(selected['occurrences'][0]['source_world_matrix'],
                             [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]])
            self.assertEqual(len(select_components(result, 'fixture')['components']), 2)
            with self.assertRaisesRegex(ValueError, 'no placed'):
                select_components(result, 'does-not-exist')

    def test_regrouping_keeps_component_ids_and_all_placements(self):
        with layer_fixture.LayerReviewTests().document(second_body=True) as doc:
            policy, motion = self.inputs(doc)
            first = build_catalog(doc, policy, motion)
            policy['groups'] = [{'product_id': 1, 'path': ['both'], 'body_ids': [6, 26], 'evidence': ['fixture']}]
            second = build_catalog(doc, policy, motion)
            self.assertEqual(first['occurrences'], second['occurrences'])
            self.assertEqual([c['id'] for c in first['components']], [c['id'] for c in second['components']])

    def test_bad_policy_pin_ownership_overlap_and_names_fail(self):
        with layer_fixture.LayerReviewTests().document(second_body=True) as doc:
            policy, motion = self.inputs(doc)
            stale = copy.deepcopy(policy)
            stale['source_sha256'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                build_catalog(doc, stale, motion)
            for ids in ([999], [6, 6]):
                bad = {**policy, 'groups': [{'product_id': 1, 'path': ['bad'], 'body_ids': ids, 'evidence': ['fixture']}]}
                with self.assertRaisesRegex(ValueError, 'overlap|outside'):
                    build_catalog(doc, bad, motion)
            bad = {**policy, 'groups': [dict(product_id=1, path=['a'], body_ids=[6], evidence=['fixture']),
                                      dict(product_id=1, path=['a', 'b'], body_ids=[26], evidence=['fixture'])]}
            with self.assertRaisesRegex(ValueError, 'paths overlap'):
                build_catalog(doc, bad, motion)
            with self.assertRaisesRegex(ValueError, 'name every'):
                build_catalog(doc, {**policy, 'product_names': {}}, motion)

    def test_assembly_selection_filters_instances_of_shared_definitions(self):
        catalog = {'source_sha256': 'fixture', 'assemblies': [{'name': 'left', 'product_id': 10}],
                   'components': [{'id': 'p2.b3', 'group': 'shared/other-bodies'}],
                   'occurrences': [{'component_id': 'p2.b3', 'ancestor_product_ids': [1, 10, 2], 'occurrence_path': [11, 12]},
                                   {'component_id': 'p2.b3', 'ancestor_product_ids': [1, 20, 2], 'occurrence_path': [21, 22]}]}
        selected = select_components(catalog, 'left')
        self.assertEqual(len(selected['occurrences']), 1)
        self.assertEqual(selected['occurrences'][0]['occurrence_path'], [11, 12])

    def test_step_work_export_preserves_original_geometry_styles_and_source(self):
        with layer_fixture.LayerReviewTests().document(second_body=True) as doc, tempfile.TemporaryDirectory() as tmp:
            policy, motion = self.inputs(doc)
            selected = select_components(build_catalog(doc, policy, motion), 'p1.b6')
            out = Path(tmp)/'component'
            export_selection(doc, selected, out)
            with CadDocument.from_step(out/'source.step', workers=1) as exported:
                self.assertEqual([b.id for b in exported.entities('SHELL_BASED_SURFACE_MODEL')], [6])
                self.assertEqual(exported.entity(8).raw, doc.entity(8).raw)
                self.assertEqual(exported.entity(19).raw, doc.entity(19).raw)
                self.assertEqual(exported.entity(12).raw, doc.entity(12).raw)
            self.assertTrue((out/'selection.json').is_file())
            with self.assertRaisesRegex(ValueError, 'exists'):
                export_selection(doc, selected, out)
            forged = copy.deepcopy(selected)
            forged['components'][0]['body_id'] = 999
            with self.assertRaisesRegex(ValueError, 'ownership'):
                export_selection(doc, forged, Path(tmp)/'bad')


if __name__ == '__main__':
    unittest.main()
