# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Pooled memberships keep names, order, multiplicity and exporter behavior."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
from cad_document import CadDocument
from p21index import Index, build_index
from p21model import Model
from p21split import Splitter, gather_refs
from test_p21model import FIXTURE

LAYERS = """#20=PRESENTATION_LAYER_ASSIGNMENT('literal #999; and ''quoted''','first',(#8,#6,#8));
#21=PRESENTATION_LAYER_ASSIGNMENT('second','description differs',(#8,#6,#8));
#22=PRESENTATION_LAYER_ASSIGNMENT('reversed','',(#6,#8,#8));
#23=PRESENTATION_LAYER_ASSIGNMENT('whitespace','',( #8 , #6, #8 ));
#24=PRESENTATION_LAYER_ASSIGNMENT('comment /* not syntax */','',(/* #999 and ) ; */ #8,#6,#8));
#25=PRESENTATION_LAYER_ASSIGNMENT('empty','',());
#26=PRESENTATION_LAYER_ASSIGNMENT('empty too','',());
#27=PRESENTATION_LAYER_ASSIGNMENT('one','',(#8));
#28=PRESENTATION_LAYER_ASSIGNMENT('same set less multiplicity','',(#8,#6));
"""


class InternedLayerTests(unittest.TestCase):
    def fixture(self, root):
        path = root / 'source.step'
        path.write_text(FIXTURE.replace('ENDSEC;\nEND-ISO-10303-21;', LAYERS + 'ENDSEC;\nEND-ISO-10303-21;'))
        return path

    def compare(self, legacy, shared):
        for field in ('ids', 'types', 'starts', 'lens'):
            np.testing.assert_array_equal(getattr(legacy, field), getattr(shared, field))
        for row in range(legacy.n):
            np.testing.assert_array_equal(legacy.refs_of(row), shared.refs_of(row))
            self.assertEqual(legacy.text(row), shared.text(row))
        self.assertEqual(legacy.reference_count, shared.reference_count)
        self.assertLess(len(shared.refs), len(legacy.refs))
        for rows in (np.arange(legacy.n), np.array([shared.r(21), shared.r(20), shared.r(22), shared.r(21)]), np.array([], dtype=int)):
            a = gather_refs(legacy, rows); b = gather_refs(shared, rows)
            for x, y in zip(a, b):
                np.testing.assert_array_equal(x, y)

    def test_parser_fallback_order_duplicates_names_and_shared_readonly_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.fixture(Path(tmp))
            with Index.from_step(source) as legacy, Index.from_step(source, intern_layers=True) as shared:
                self.compare(legacy, shared)
                self.assertTrue(shared.layers_interned)
                self.assertTrue(np.shares_memory(shared.refs_of(shared.r(20)), shared.refs_of(shared.r(21))))
                self.assertTrue(np.shares_memory(shared.refs_of(shared.r(20)), shared.refs_of(shared.r(23))))
                self.assertTrue(np.shares_memory(shared.refs_of(shared.r(20)), shared.refs_of(shared.r(24))))
                self.assertNotEqual(shared.layer_membership_key(shared.r(20)), shared.layer_membership_key(shared.r(22)))
                with self.assertRaises(ValueError):
                    shared.refs_of(shared.r(20))[0] = 6

    def test_parallel_chunks_and_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = self.fixture(root)
            data = build_index(source, workers=2, chunks_per_worker=4, intern_layers=True)
            np.savez(root/'shared.npz', **data)
            with Index.from_step(source) as legacy, Index(root/'shared.npz') as shared:
                self.compare(legacy, shared)

    def test_splitter_filters_layer_memberships_identically(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.fixture(Path(tmp))
            # Restrict to plain list syntax supported by the existing splitter.
            source.write_text(source.read_text().replace(LAYERS, '\n'.join(LAYERS.splitlines()[:4])+'\n'))
            outputs = []
            for compact in (False, True):
                with CadDocument.from_step(source, intern_layers=compact) as doc:
                    split = Splitter(doc.index, doc.model)
                    mask, rewritten = split.closure_products([doc.index.r(1)])
                    path = Path(tmp) / f'export-{compact}.step'
                    split.write_closure(mask, rewritten, path)
                    outputs.append(path.read_bytes())
            # Split headers include the output filename. Compare DATA, retaining
            # the names/descriptions of every separate layer in the result.
            self.assertEqual(outputs[0].split(b'DATA;')[1], outputs[1].split(b'DATA;')[1])
            self.assertIn(b"'second'", outputs[1])

    def test_no_layers_is_valid_and_legacy_cache_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'source.step';source.write_text(FIXTURE)
            np.savez(root/'legacy.npz', **build_index(source, workers=1))
            with Index(root/'legacy.npz') as old, Index.from_step(source, intern_layers=True) as new:
                self.assertFalse(old.layers_interned)
                self.assertEqual(new.reference_count, old.reference_count)
                np.testing.assert_array_equal(old.refs, new.refs)

    def test_unresolved_reference_counts_preserve_logical_multiplicity(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=self.fixture(Path(tmp))
            missing="\n#90=PRESENTATION_LAYER_ASSIGNMENT('missing','',(#999,#999));\n#91=PRESENTATION_LAYER_ASSIGNMENT('also missing','',(#999,#999));\n"
            source.write_text(source.read_text().replace('ENDSEC;\nEND-ISO-10303-21;',missing+'ENDSEC;\nEND-ISO-10303-21;'))
            for compact in (False,True):
                with Index.from_step(source,intern_layers=compact) as ix:
                    self.assertEqual(ix.unresolved_reference_count(),4)


if __name__ == '__main__':
    unittest.main()
