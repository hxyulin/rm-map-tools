# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Spatial grouping distinguishes whole containers, shells and ambiguous intersections."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
from audit_component_regions import audit_regions, classify_box
from cad_components import build_catalog
import test_review_cad_layers as fixture

UNITS = """
#90=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
#91=(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNIT_ASSIGNED_CONTEXT((#90))REPRESENTATION_CONTEXT('',''));
"""


class ComponentRegionTests(unittest.TestCase):
    def plan(self, doc):
        return {'schema_version': 1, 'source_sha256': doc.source_sha256,
                'coordinate_frame': 'product-local', 'length_unit': 'millimetre',
                'surface_model_body_ids': [26],
                'regions': [{'id': 'part/region', 'product_id': 1, 'min_mm': [-1., -1., -1.],
                             'max_mm': [1., 1., 1.], 'expected_body_ids': [6], 'evidence': ['fixture']}]}

    def bounds(self, doc, *, large_parent=True):
        def read(row):
            source = int(doc.index.ids[row])
            half = 3. if large_parent and source == 26 else .5
            return np.full(3, -half), np.full(3, half), 8
        return patch.object(doc.model, 'body_bbox', side_effect=read)

    def test_center_inside_does_not_assign_a_spanning_body_but_existing_shell_can_match(self):
        with fixture.LayerReviewTests().document(UNITS, second_body=True) as doc, self.bounds(doc):
            result = audit_regions(doc, self.plan(doc), fixture.LayerReviewTests().profile(doc))
            region = result['regions'][0]
            self.assertEqual(region['contained_body_ids'], [6])
            self.assertEqual(region['straddling_body_ids'], [26])
            self.assertEqual(region['shell_candidates']['contained_shell_ids'], [27])
            self.assertTrue(region['expected_membership_matches'])
            self.assertEqual(region['qualification'], 'spatial-candidate')
            self.assertFalse(region['shell_motion_filter_applied'])

    def test_explicit_motion_filter_cannot_treat_unknown_as_fixed(self):
        with fixture.LayerReviewTests().document(UNITS, second_body=True) as doc, self.bounds(doc, large_parent=False):
            plan = self.plan(doc)
            plan['regions'][0]['expected_body_ids'] = [26]
            plan['regions'][0]['motion_filter'] = {'motion': 'fixed', 'motion_owner': '26'}
            profile = fixture.LayerReviewTests().profile(doc, [(26, 'fixed')])
            region = audit_regions(doc, plan, profile)['regions'][0]
            self.assertEqual(region['contained_body_ids'], [26])
            self.assertEqual(region['excluded_by_motion_body_ids'], [6])
            self.assertTrue(region['expected_membership_matches'])

    def test_overlapping_shell_matches_are_not_automatically_assigned(self):
        with fixture.LayerReviewTests().document(UNITS, second_body=True) as doc, self.bounds(doc):
            plan = self.plan(doc)
            plan['regions'].append({**copy.deepcopy(plan['regions'][0]), 'id': 'part/overlap'})
            result = audit_regions(doc, plan, fixture.LayerReviewTests().profile(doc))
            self.assertEqual(result['shells_in_multiple_regions'],
                             [{'shell_id': 27, 'regions': ['part/region', 'part/overlap']}])

    def test_stale_units_and_wrong_expected_ownership_are_rejected(self):
        with fixture.LayerReviewTests().document(UNITS, second_body=True) as doc, self.bounds(doc):
            profile = fixture.LayerReviewTests().profile(doc)
            plan = self.plan(doc)
            for key, value in [('source_sha256', 'wrong'), ('coordinate_frame', 'world'), ('length_unit', 'metre')]:
                with self.assertRaises(ValueError):
                    audit_regions(doc, {**plan, key: value}, profile)
            plan['regions'][0]['expected_body_ids'] = [999]
            with self.assertRaisesRegex(ValueError, 'owned'):
                audit_regions(doc, plan, profile)

    def test_candidate_catalog_group_requires_matching_region_evidence(self):
        with fixture.LayerReviewTests().document(UNITS, second_body=True) as doc, self.bounds(doc):
            profile = fixture.LayerReviewTests().profile(doc)
            plan = self.plan(doc)
            policy = {'schema_version': 1, 'source_sha256': doc.source_sha256,
                      'product_names': {'1': 'part'}, 'groups': [
                          {'product_id': 1, 'path': ['region'], 'body_ids': [6], 'evidence': ['fixture'],
                           'review_status': 'spatial-candidate', 'region_id': 'part/region'}]}
            with self.assertRaisesRegex(ValueError, 'require.*region plan'):
                build_catalog(doc, policy, profile)
            result = build_catalog(doc, policy, profile, plan)
            self.assertEqual(result['components'][0]['group_review_status'], 'spatial-candidate')
            policy['groups'][0]['body_ids'] = [26]
            with self.assertRaisesRegex(ValueError, 'disagrees'):
                build_catalog(doc, policy, profile, plan)

    def test_box_with_missing_vertices_remains_unbounded(self):
        with fixture.LayerReviewTests().document(UNITS, second_body=True) as doc:
            with patch.object(doc.model, 'body_bbox', return_value=(None, None, 0)):
                region = audit_regions(doc, self.plan(doc), fixture.LayerReviewTests().profile(doc))['regions'][0]
                self.assertEqual(region['unbounded_body_ids'], [6, 26])
                self.assertFalse(region['expected_membership_matches'])
                self.assertEqual(region['shell_candidates']['unbounded_shell_ids'], [27])


if __name__ == '__main__':
    unittest.main()
