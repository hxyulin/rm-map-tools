# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only discovery preserves occurrences and rejects uncertain placement data."""
from types import SimpleNamespace
import unittest
import numpy as np
from audit_cad_passes import PASSES, assembly_reuse, exact_body_reuse, rigid, run
from unittest.mock import patch


class FakeIndex:
    def __init__(self, records):
        self.records = records
        self.ids = np.arange(max(20, max(records)+1))

    def text(self, row):
        return self.records[row]

    def r(self, number):
        return number if number in self.records else -1

    def tname(self, row):
        return self.records[row].split(b'=', 1)[1].split(b'(', 1)[0].decode()

    def rows_of(self, *names):
        return np.array([r for r in self.records if self.tname(r) in names])


class CadPassTests(unittest.TestCase):
    def model(self):
        return SimpleNamespace(roots=[1], children={1: [(10, 2), (11, 2)]},
                               pname=lambda p: 'product-'+str(p), product_reps={1: [], 2: []})

    def test_repeated_products_keep_paths_and_both_world_transforms(self):
        ix = SimpleNamespace(ids=np.arange(20))
        shifted = np.eye(4)
        shifted[0, 3] = 123
        result = assembly_reuse(ix, self.model(), {10: np.eye(4), 11: shifted})
        self.assertEqual(result['additional_product_occurrences'], 1)
        instances = result['groups'][0]['occurrences']
        self.assertEqual([p['occurrence_path'] for p in instances], [[10], [11]])
        self.assertEqual(instances[1]['source_world_matrix'][0][3], 123)
        # No occurrence was removed even when storage might be shared.
        self.assertEqual(result['placed_product_occurrences'], 3)

    def test_missing_or_reflected_placements_never_become_identity_instances(self):
        ix = SimpleNamespace(ids=np.arange(20))
        for transforms in ({}, {10: np.diag([-1., 1, 1, 1])}):
            result = assembly_reuse(ix, self.model(), transforms)
            self.assertEqual(result['placed_product_occurrences'], 1)
            self.assertEqual(len(result['issues']), 2)

    def test_cycle_is_rejected(self):
        model = self.model()
        model.children[2] = [(12, 1)]
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            assembly_reuse(SimpleNamespace(ids=np.arange(20)), model,
                           {r: np.eye(4) for r in [10, 11, 12]})

    def test_body_hash_shares_geometry_only_and_preserves_owners(self):
        ix = FakeIndex({1: b"#1=CARTESIAN_POINT('a',(1.,2.,3.));",
                        2: b"#2=CARTESIAN_POINT('b',(1.,2.,3.));",
                        3: b"#3=MANIFOLD_SOLID_BREP('original',#1);",
                        4: b"#4=MANIFOLD_SOLID_BREP('copy', /* #999 */ #2);",
                        5: b"#5=CARTESIAN_POINT('',(1.,2.,3.00001));",
                        6: b"#6=MANIFOLD_SOLID_BREP('changed',#5);"})
        model = SimpleNamespace(bodies=[(3, 10), (4, 11), (6, 12)],
                                rep_product={10: 13, 11: 14, 12: 15})
        result = exact_body_reuse(ix, model)
        self.assertEqual(result['redundant_body_definitions'], 1)
        group = result['groups'][0]
        self.assertEqual([b['owner_product_ids'] for b in group['bodies']], [[13], [14]])
        self.assertIn('not checked', group['appearance_equivalence'])
        self.assertEqual(result['body_definitions'], 3)

    def test_scaling_shear_and_nonfinite_transforms_are_rejected(self):
        for matrix in (np.diag([2., 1, 1, 1]), np.ones((4, 4)), np.full((4, 4), np.nan)):
            self.assertFalse(rigid(matrix))

    def test_unregistered_or_duplicate_passes_are_refused_before_io(self):
        for names in ([], ['unknown'], ['assembly-reuse', 'assembly-reuse']):
            with self.assertRaises(ValueError):
                run('does-not-exist.npz', 'unused', names)

    def test_mutating_registry_entry_is_refused_before_io(self):
        with patch.dict(PASSES, {'writes-cad': {'effect': 'mutating'}}):
            with self.assertRaisesRegex(ValueError, 'read-only'):
                run('does-not-exist.npz', 'unused', ['writes-cad'])


if __name__ == '__main__':
    unittest.main()
