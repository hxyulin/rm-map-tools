# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Exercise overlap precedence and replay references with independently owned shells."""
import unittest
import numpy as np
from cad_pass_composition import compose_shells


class CompositionTests(unittest.TestCase):
    def test_replay_uses_edited_source_and_preserves_other_shells(self):
        source = {'positions_mm': np.arange(27, dtype=float).reshape(-1, 3),
                  'triangles': np.arange(9).reshape(-1, 3),
                  'material_ids': np.array([4, 5, 6]), 'unit_ids': np.array([1, 2, 3])}
        edited = {k: v.copy() for k, v in source.items()}
        edited['positions_mm'][:3] += .125
        # Hardware shell 2 is absent, while shell 3 is an independently qualified cavity.
        edited['triangles'] = edited['triangles'][[0, 2]]
        edited['material_ids'] = edited['material_ids'][[0, 2]]
        edited['unit_ids'] = edited['unit_ids'][[0, 2]]
        calls = []
        def replay(unit, p, t, m):
            calls.append(unit)
            np.testing.assert_array_equal(p[t], edited['positions_mm'][edited['triangles'][:1]])
            return p, t, m, {'checked': True}
        p, t, m, u, records = compose_shells(source, edited, [1, 2], replay)
        self.assertEqual(calls, [1]); self.assertEqual(u.tolist(), [1, 3])
        np.testing.assert_array_equal(p[t[u == 3]], source['positions_mm'][source['triangles'][2:]])
        self.assertEqual(records[1]['operation'], 'selected-hardware-omission')
        p, t, m, u, records = compose_shells(source, edited, [1, 2], replay, omit_units=[3])
        self.assertEqual(u.tolist(), [1])
        with self.assertRaises(ValueError): compose_shells(source, edited, [99], replay)
