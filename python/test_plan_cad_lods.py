# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source hierarchy adapter invariants without a CAD kernel or production CAD."""
from copy import deepcopy
import unittest
from plan_cad_lods import IDENTITY, build_plan, matrix, scale_bound


def fixture():
    shifted = deepcopy(IDENTITY)
    shifted[0][3] = 100
    return {'schema_version': 1, 'source_geometry_preserved': True,
            'assembly_graph_verified': True, 'source_world_placements_verified': True,
            'source_face_definitions': 2, 'expected_placed_faces': 4, 'root_product_id': 1,
            'components': [{'id': 'plate', 'export_product_id': 2, 'source_product_id': 9,
                            'face_ids': [10, 11], 'face_count': 2, 'review_status': 'partition-only'}],
            'assemblies': [{'name': 'root', 'product_id': 1,
                            'children': [{'product_id': 2, 'matrix_mm': IDENTITY},
                                         {'product_id': 2, 'matrix_mm': shifted}]}]}


class HierarchyLodTests(unittest.TestCase):
    def test_placements_remain_separate_and_profiles_share(self):
        catalog = fixture()
        result = build_plan(catalog)
        self.assertEqual(result['summary']['placed_component_uses'], 2)
        self.assertEqual(result['summary']['pooled_request_profiles'], 4)
        # Near visual and fixed collision have identical quality but different
        # channels remain explicit until a validated mesh payload can be shared.
        self.assertEqual(len(result['bindings']), 8)
        self.assertNotEqual(result['nodes'][1]['id'], result['nodes'][2]['id'])
        self.assertEqual(result['nodes'][2]['world_matrix_mm'][0][3], 100)
        self.assertEqual(catalog, fixture())

    def test_selective_override_applies_to_all_definition_uses(self):
        result = build_plan(fixture(), overrides={
            'plate': {'visual': {'far': {'total_mm': .4, 'mesh_mm': .3}}}})
        profiles = [p for p in result['request_profiles'].values()
                    if p['channel'] == 'visual' and p['quality_local_mm']['total_mm'] > .2]
        self.assertTrue(any(abs(p['quality_local_mm']['total_mm'] - .4) < 1e-12 for p in profiles))
        with self.assertRaisesRegex(ValueError, 'protected'):
            build_plan(fixture(), overrides={
                'plate': {'visual': {'far': {'total_mm': 1, 'fit_mm': .1}}}})
        with self.assertRaises(ValueError):
            build_plan(fixture(), overrides={'typo': {}})

    def test_face_coverage_and_placed_accounting_are_required(self):
        for field, value in [('expected_placed_faces', 3), ('source_face_definitions', 3)]:
            bad = fixture()
            bad[field] = value
            with self.assertRaises(ValueError):
                build_plan(bad)
        bad = fixture()
        bad['components'][0]['face_ids'] = [10, 10]
        with self.assertRaises(ValueError):
            build_plan(bad)

    def test_graph_failures_abort_instead_of_dropping_geometry(self):
        for child in [1, 99]:
            bad = fixture()
            bad['assemblies'][0]['children'][0]['product_id'] = child
            with self.assertRaises(ValueError):
                build_plan(bad)
        bad = fixture()
        bad['assemblies'].append({'name': 'orphan', 'product_id': 88, 'children': []})
        with self.assertRaisesRegex(ValueError, 'unreachable'):
            build_plan(bad)

    def test_visual_only_definition_has_no_collision_requests(self):
        from cad_collision_roles import CollisionRoles
        catalog = fixture(); catalog['files_sha256'] = {'field.step':'a'*64}
        roles = CollisionRoles({'schema_version':1,'source_sha256':'a'*64,
            'hierarchy_sha256':'b'*64,'entries':[{'component_id':'plate','role':'marking',
            'visual':True,'collision':False,'selection':'component','source_face_ids':[10,11],
            'backing_required':False}]},catalog,hierarchy_sha256='b'*64)
        result = build_plan(catalog,roles=roles)
        self.assertEqual(len(result['bindings']),6)
        self.assertFalse(result['definitions'][0]['collision_enabled'])
        self.assertTrue(all(p['channel']=='visual' for p in result['request_profiles'].values()))

    def test_scaled_placements_and_invalid_transforms(self):
        value = deepcopy(IDENTITY)
        value[0][0] = -2
        self.assertGreaterEqual(scale_bound(matrix(value)), 2)
        bad = fixture()
        bad['assemblies'][0]['children'][1]['matrix_mm'] = value
        result = build_plan(bad)
        self.assertGreater(result['summary']['pooled_request_profiles'], 4)
        value[2][2] = 0
        with self.assertRaises(ValueError):
            matrix(value)


if __name__ == '__main__':
    unittest.main()
