# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Metadata array sharing counts retain distinct layer records and names."""
from pathlib import Path
import tempfile
import unittest
from audit_step_storage import layers, measure
from p21index import Index
from test_cad_share_values import HEADER, UNITS


class StorageAuditTests(unittest.TestCase):
    def test_identical_lists_intern_without_merging_layer_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step = root / 'field.step'
            step.write_bytes(HEADER + ("#1=CARTESIAN_POINT('',(0.,0.,0.));\n"
                "#2=PRESENTATION_LAYER_ASSIGNMENT('one','',(#1));\n"
                "#3=PRESENTATION_LAYER_ASSIGNMENT('two','',(#1));\n" + UNITS).encode() + b'ENDSEC;\nEND-ISO-10303-21;\n')
            (root / 'metadata.json').write_text('{}\n')
            with Index.from_step(step) as ix:
                result = layers(ix)
                self.assertEqual(result['records'], 2)
                self.assertEqual(result['unique_ordered_membership_lists'], 1)
                self.assertEqual(result['reference_array_bytes'], 8)
                self.assertEqual(result['interned_reference_array_bytes'], 4)
            result = measure(root)
            self.assertEqual(set(result['zip_entries']), {'field.step', 'metadata.json'})
            self.assertEqual(result['package_bytes'], step.stat().st_size + 3)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['field.step', 'metadata.json'])


if __name__ == '__main__':
    unittest.main()
