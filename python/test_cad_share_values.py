# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Sharing preserves topology, semantic handles, paint targets and literal bytes."""
from pathlib import Path
import tempfile
import unittest

from cad_share_values import plan_sharing, write_shared, validate_shared, run
from p21index import Index

HEADER = b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\nENDSEC;\nDATA;\n"
UNITS = "#900=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));\n#901=(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNIT_ASSIGNED_CONTEXT((#900))REPRESENTATION_CONTEXT('',''));\n"
RECORDS = """#1=CARTESIAN_POINT('',(0.,0.,0.));
#2=CARTESIAN_POINT('',(0.,0.,0.));
#3=CARTESIAN_POINT('construction',(0.,0.,0.));
#4=CARTESIAN_POINT('',(0.0,0.,0.));
#5=CARTESIAN_POINT('',(0.,0.,0.));
#6=CARTESIAN_POINT('',(0.,0.,0.));
#7=CARTESIAN_POINT('',(0.,0.,0.));
#8=VERTEX_POINT('',#1);
#9=VERTEX_POINT('',#2);
#10=AXIS2_PLACEMENT_3D('',#5,$,$);
#11=SHAPE_REPRESENTATION('',(#10),#901);
#12=DIRECTION('',(1.,0.,0.));
#13=DIRECTION('',(1.,0.,0.));
#14=VECTOR('',#12,1.);
#15=VECTOR('',#13,1.);
#20=COLOUR_RGB('literal #2',1.,0.,0.);
#21=COLOUR_RGB('literal #2',1.,0.,0.);
#22=COLOUR_RGB('another name',1.,0.,0.);
#23=FILL_AREA_STYLE_COLOUR('',#20);
#24=FILL_AREA_STYLE_COLOUR('',#21);
#25=PRESENTATION_STYLE_ASSIGNMENT((#23));
#26=PRESENTATION_STYLE_ASSIGNMENT((#24));
#27=STYLED_ITEM('',(#25),#6);
#28=STYLED_ITEM('',(#26),#9);
#29=PRESENTATION_LAYER_ASSIGNMENT('layer','literal #2',(#7));
#30=CARTESIAN_POINT('',(0.,0.,0.));
#31=OVER_RIDING_STYLED_ITEM('',(#26),#30,#28);
"""


class ValueSharingTests(unittest.TestCase):
    def fixture(self, root, records=RECORDS, units=UNITS):
        path = root / 'source.step'
        path.write_bytes(HEADER + (records + units).encode() + b'ENDSEC;\nEND-ISO-10303-21;\n')
        return path

    def test_exact_values_share_but_topology_and_semantic_handles_stay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root)
            with Index.from_step(path) as ix:
                aliases, _ = plan_sharing(ix)
                self.assertEqual(aliases, {2: 1, 13: 12, 15: 14, 21: 20, 24: 23, 26: 25})
                write_shared(ix, aliases, root / 'shared.step')
                with Index.from_step(root / 'shared.step') as shared:
                    proof = validate_shared(ix, shared, aliases)
                    self.assertTrue(proof['all_references_resolve'])
                    self.assertEqual(shared.text(shared.r(9)), b"#9=VERTEX_POINT('',#1);")
                    self.assertEqual(shared.text(shared.r(28)), b"#28=STYLED_ITEM('',(#25),#9);")
                    self.assertIn(b"'literal #2'", shared.text(shared.r(20)))
                    self.assertEqual(shared.text(shared.r(29)), ix.text(ix.r(29)))
                    self.assertGreaterEqual(shared.r(30), 0)
                    self.assertFalse(plan_sharing(shared)[0])

    def test_output_tampering_is_detected_in_entities_and_header(self):
        for before, after in [(b"FILE_SCHEMA", b"WRONG_SCHEMA"), (b"#9=VERTEX_POINT('',#1)", b"#9=VERTEX_POINT('',#3)")]:
            with self.subTest(before=before), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = self.fixture(root); output = root / 'shared.step'
                with Index.from_step(path) as ix:
                    aliases, _ = plan_sharing(ix); write_shared(ix, aliases, output)
                    output.write_bytes(output.read_bytes().replace(before, after))
                    with Index.from_step(output) as shared, self.assertRaises(ValueError):
                        validate_shared(ix, shared, aliases)

    def test_policy_rejects_removing_a_named_handle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root)
            with Index.from_step(path) as ix:
                aliases, _ = plan_sharing(ix); aliases[3] = 1
                write_shared(ix, aliases, root / 'shared.step')
                with Index.from_step(root / 'shared.step') as shared, self.assertRaisesRegex(ValueError, 'policy'):
                    validate_shared(ix, shared, aliases)

    def test_unknown_units_and_style_cycles_fail_closed(self):
        for records, units, error in [(RECORDS, '', 'length unit'),
                                      ("#1=FILL_AREA_STYLE('',(#2));\n#2=FILL_AREA_STYLE('',(#1));\n", UNITS, 'cyclic')]:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as tmp:
                path = self.fixture(Path(tmp), records, units)
                with Index.from_step(path) as ix, self.assertRaisesRegex(ValueError, error):
                    plan_sharing(ix)

    def test_existing_outputs_refused_and_failed_build_leaves_no_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.fixture(root, units=''); output = root / 'candidate'
            with self.assertRaises(ValueError):
                run(path, output)
            self.assertFalse(output.exists())
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['source.step'])
            output.mkdir()
            with self.assertRaises(FileExistsError):
                run(path, output)


if __name__ == '__main__':
    unittest.main()
