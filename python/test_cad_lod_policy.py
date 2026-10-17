# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Hierarchy, quality accumulation, cache identity and seam policy regressions."""
from dataclasses import replace
import math
import unittest
from cad_lod_policy import (Node, Quality, mesh_key, plan, projected_error_px,
                            shared_boundary_limits)


class LodPolicyTests(unittest.TestCase):
    def setUp(self):
        self.defaults = {('visual', 'near'): Quality(.1, mesh_mm=.09, quantization_mm=.01),
                         ('visual', 'far'): Quality(2, mesh_mm=1.9, quantization_mm=.1),
                         ('collision', 'fixed'): Quality(.2, mesh_mm=.2)}
        self.nodes = (Node('arena', None), Node('road', 'arena'),
                      Node('surface', 'road', 'wave'), Node('cap', 'road', 'plane'))

    def test_parent_and_leaf_overrides_preserve_other_slots(self):
        overrides = {'road': {('visual', 'far'): Quality(1, mesh_mm=1)},
                     'surface': {('visual', 'near'): Quality(.05, mesh_mm=.05)}}
        requests = {(r.node, r.channel, r.level): r for r in plan(self.nodes, self.defaults, overrides)}
        self.assertEqual(requests['surface', 'visual', 'far'].quality.total_mm, 1)
        self.assertEqual(requests['surface', 'visual', 'near'].quality.total_mm, .05)
        self.assertEqual(requests['cap', 'visual', 'near'].quality.total_mm, .1)
        self.assertEqual(requests['surface', 'collision', 'fixed'].quality.total_mm, .2)
        self.assertEqual(self.defaults['visual', 'far'].total_mm, 2)

    def test_protection_inherits_and_cannot_be_bypassed(self):
        nodes = (Node('arena', None, protected=True), Node('armor', 'arena', 'plate'))
        with self.assertRaisesRegex(ValueError, 'protected'):
            plan(nodes, self.defaults)
        exact = {k: Quality(q.total_mm, mesh_mm=q.total_mm) for k, q in self.defaults.items()}
        self.assertTrue(all(r.protected for r in plan(nodes, exact)))

    def test_world_scale_tightens_all_local_allowances(self):
        requests = plan((Node('scaled', None, 'wave', 4),), self.defaults)
        near = next(r for r in requests if r.level == 'near')
        self.assertEqual(near.quality, Quality(.025, mesh_mm=.0225, quantization_mm=.0025))

    def test_mixed_lods_use_same_fine_boundary_contract(self):
        requests = plan(self.nodes, self.defaults,
                        {'cap': {('visual', 'near'): Quality(.04, mesh_mm=.04)}})
        limits = shared_boundary_limits(requests, {'edge-9': ('surface', 'cap')})
        self.assertEqual(limits, {'edge-9': {'visual': .04, 'collision': .2}})
        with self.assertRaises(ValueError):
            shared_boundary_limits(requests, {'bad': ('missing',)})

    def test_interfaces_compare_world_errors_across_scaled_owners(self):
        nodes = (Node('a', None, 'p', 4), Node('b', None, 'q', .5))
        requests = plan(nodes, self.defaults)
        limits = shared_boundary_limits(requests, {'interface': ['a', 'b']})
        self.assertAlmostEqual(limits['interface']['visual'], .09)
        self.assertAlmostEqual(limits['interface']['collision'], .2)

    def test_cache_aliases_names_and_levels_but_not_boundaries(self):
        request = plan(self.nodes, self.defaults)[0]
        args = dict(source_sha256='a'*64, geometry_sha256='b'*64,
                    boundary_sha256='c'*64, attributes_sha256='d'*64, mesher_version='v1')
        key = mesh_key(request, **args)
        self.assertEqual(key, mesh_key(replace(request, node='other', level='alias'), **args))
        self.assertNotEqual(key, mesh_key(request, **{**args, 'boundary_sha256': 'e'*64}))
        self.assertNotEqual(key, mesh_key(replace(request, quality=Quality(.3, mesh_mm=.3)), **args))
        self.assertNotEqual(key, mesh_key(request, **{**args, 'mesher_version': 'v2'}))

    def test_invalid_policy_graphs_fail_before_meshing(self):
        for nodes in ((Node('x', 'missing'),), (Node('x', 'y'), Node('y', 'x')),
                      (Node('x', None), Node('x', None)), (Node('x', None, 'p', 0),)):
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                plan(nodes, self.defaults)
        with self.assertRaises(ValueError):
            plan(self.nodes, self.defaults, {'typo': {}})
        with self.assertRaises(ValueError):
            plan(self.nodes, {('visual', 'near'): Quality(1)})
        with self.assertRaises(ValueError):
            plan(self.nodes, self.defaults, {'road': {('visual', 'typo'): Quality(1)}})

    def test_error_stages_cannot_each_spend_whole_budget(self):
        with self.assertRaises(ValueError):
            Quality(1, fit_mm=.6, mesh_mm=.6)
        for value in (float('nan'), float('inf'), True, -1, 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Quality(value)

    def test_projected_error_scales_with_distance_and_resolution(self):
        self.assertAlmostEqual(projected_error_px(1, 1000, 1000, math.pi/2), .5)
        self.assertAlmostEqual(projected_error_px(1, 2000, 2000, math.pi/2), .5)
        for args in ((1, 0, 1000, 1), (1, 10, 1000, math.pi), (-1, 10, 1000, 1)):
            with self.assertRaises(ValueError):
                projected_error_px(*args)


if __name__ == '__main__':
    unittest.main()
