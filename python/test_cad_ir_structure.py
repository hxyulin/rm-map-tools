# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Typed reconstruction, graph identity and incidence counterexamples."""
from pathlib import Path
import re
import tempfile
import unittest

import numpy as np
from cad_document import CadDocument
from cad_optimizer import build_pool
from cad_ir_structure import (typed_records, topology_uses, stable_recipe_hashes,
                              incidence_hash, cache_context, PASS_CONTRACTS)
from test_cad_optimizer import RECORDS
from test_cad_share_values import UNITS
from test_p21model import FIXTURE

GRAPH = """#300=EDGE_CURVE('',#102,#102,#120,.T.);
#301=EDGE_CURVE('',#102,#103,#120,.T.);
#302=ORIENTED_EDGE('',*,*,#300,.F.);
#303=EDGE_LOOP('',(#302,#302));
#304=FACE_OUTER_BOUND('',#303,.F.);
#305=ADVANCED_FACE('',(#304),#124,.T.);
#306=EDGE_CURVE('',#103,#103,#121,.T.);
"""


class StructureTests(unittest.TestCase):
    def source(self, root, suffix='', renumber=False):
        text=FIXTURE.replace('ENDSEC;\nEND-ISO-10303-21;',RECORDS+GRAPH+UNITS+'ENDSEC;\nEND-ISO-10303-21;')
        if renumber:
            # Never rewrite quoted labels when renumbering references.
            text=re.sub(r"'(?:[^']|'')*'|#(\d+)",lambda m:'#'+str(int(m[1])+1000) if m[1] else m[0],text)
        path=root/('source'+suffix+'.step');path.write_text(text);return path

    def test_typed_roundtrip_and_explicit_topology(self):
        with tempfile.TemporaryDirectory() as tmp, CadDocument.from_step(self.source(Path(tmp))) as doc:
            for normalize in (False,True):
                pool=build_pool(doc,[doc.index.r(v) for v in (305,301,180)],decimals=normalize,display_names=True)
                typed=typed_records(pool)
                for recipe in range(len(pool.kinds)):
                    self.assertEqual(typed.reconstruct(recipe),pool.record(recipe))
                uses=topology_uses(pool)
                self.assertEqual(uses.children(303).tolist(),[302,302])
                self.assertEqual(uses.children(301).tolist(),[102,103,120])
                self.assertEqual(uses.use(301).roles(),{'start_vertex':102,'end_vertex':103,'curve':120})
                self.assertEqual(uses.use(305).roles(),{'bounds':(304,),'surface':124})
                self.assertFalse(uses.use(302).orientation)
                self.assertEqual(uses.use(303).roles(),{'oriented_edges':(302,302)})
                senses=dict(zip(uses.source_ids,uses.orientations))
                self.assertEqual(senses[302],0);self.assertEqual(senses[304],0);self.assertEqual(senses[305],1)
                with self.assertRaises(ValueError):uses.references[0]=0
                with self.assertRaises(ValueError):uses.children(180)
                self.assertGreater(typed.statistics()['reference_operands'],0)

    def test_stable_keys_preserve_aliases_and_ignore_numbering_and_root_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with CadDocument.from_step(self.source(root)) as a, CadDocument.from_step(self.source(root,'b',True)) as b:
                pa=build_pool(a,[a.index.r(v) for v in (300,301,306)],decimals=True,display_names=True)
                pb=build_pool(b,[b.index.r(v) for v in (1306,1301,1300)],decimals=True,display_names=True)
                ca,cb=cache_context(a),cache_context(b)
                self.assertEqual(ca,cb)
                ha,hb=stable_recipe_hashes(pa,ca),stable_recipe_hashes(pb,cb)
                # Same mathematical recipe, different alias patterns.
                self.assertEqual(pa.recipe_for_source(300),pa.recipe_for_source(301))
                self.assertNotEqual(incidence_hash(pa,300,ca),incidence_hash(pa,301,ca))
                for source in (300,301,306):
                    self.assertTrue(np.array_equal(ha[pa.recipe_for_source(source)],hb[pb.recipe_for_source(source+1000)]))
                    self.assertEqual(incidence_hash(pa,source,ca),incidence_hash(pb,source+1000,cb))
                self.assertFalse(np.array_equal(ha,stable_recipe_hashes(pa,b'changed tolerance')))
                self.assertEqual(len(PASS_CONTRACTS),4)

    def test_tolerance_is_a_cache_dimension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); first=self.source(root)
            text=first.read_text().replace("GLOBAL_UNIT_ASSIGNED_CONTEXT((#900))",
                "GLOBAL_UNIT_ASSIGNED_CONTEXT((#900))GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#902))")
            text=text.replace('ENDSEC;\nEND-ISO-10303-21;',
                "#902=UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.001),#900,'','');\nENDSEC;\nEND-ISO-10303-21;")
            first.write_text(text);second=root/'tolerance.step'
            second.write_text(text.replace('LENGTH_MEASURE(0.001)','LENGTH_MEASURE(0.002)'))
            with CadDocument.from_step(first) as a, CadDocument.from_step(second) as b:
                self.assertNotEqual(cache_context(a),cache_context(b))



if __name__=='__main__':unittest.main()
