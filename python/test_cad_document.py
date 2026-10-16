# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Direct STEP documents retain exact metadata and load working CAD only on demand."""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np
from cad_document import CadDocument
from audit_cad_passes import run_document
from export_field_package import GlbWriter
from gltf_scene import read_glb, read_glb_local_nodes

FIXTURE = """ISO-10303-21;
HEADER;
ENDSEC;
DATA;
#1=PRODUCT('part','part','',(#4));
#2=PRODUCT_DEFINITION_FORMATION('','',#1);
#3=PRODUCT_DEFINITION('','',#2,$);
#4=PRODUCT_CONTEXT('','part definition',$);
#5=PRODUCT_DEFINITION_SHAPE('','',#3);
#6=SHELL_BASED_SURFACE_MODEL('',(#7));
#7=OPEN_SHELL('',(#8));
#8=ADVANCED_FACE('',(),$,.T.);
#9=SHAPE_DEFINITION_REPRESENTATION(#5,#10);
#10=MANIFOLD_SURFACE_SHAPE_REPRESENTATION('',(#6),$);
#12=COLOUR_RGB('precise',0.123456789,0.2,0.3);
#13=FILL_AREA_STYLE_COLOUR('',#12);
#14=FILL_AREA_STYLE('',(#13));
#15=SURFACE_STYLE_FILL_AREA(#14);
#16=SURFACE_SIDE_STYLE('',(#15));
#17=SURFACE_STYLE_USAGE(.NEGATIVE.,#16);
#18=PRESENTATION_STYLE_ASSIGNMENT((#17));
#19=STYLED_ITEM('',(#18),#8);
#20=PRESENTATION_LAYER_ASSIGNMENT('paint','literal #555',(#8));
ENDSEC;
END-ISO-10303-21;
"""


class CadDocumentTests(unittest.TestCase):
    def test_direct_step_preserves_metadata_without_creating_cache_or_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.step'
            path.write_text(FIXTURE)
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            with CadDocument.from_step(path, workers=1, expected_sha256=expected) as document:
                layer = next(document.entities('PRESENTATION_LAYER_ASSIGNMENT'))
                self.assertEqual(layer.strings, ('paint', 'literal #555'))
                self.assertEqual(layer.reference_ids.tolist(), [8])
                self.assertFalse(layer.reference_ids.flags.writeable)
                self.assertIn(b'0.123456789', document.entity(12).raw)
                self.assertIn(b'.NEGATIVE.', document.entity(17).raw)
                self.assertEqual(document.styles(8)[0].id, 19)
                self.assertIsNone(document._working)
                identity = document.node_identity(document.index.r(1))
                self.assertEqual(identity['body_ids'], [6])
                report = run_document(document, ['exact-body-reuse'])
                self.assertEqual(report['passes'][0]['findings']['body_definitions'], 1)
                self.assertEqual(set(p.name for p in Path(tmp).iterdir()), {'source.step'})
                document.verify_source()
            with self.assertRaisesRegex(ValueError, 'closed'):
                _ = layer.raw
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_wrong_source_pin_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.stp'
            path.write_text(FIXTURE)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                CadDocument.from_step(path, workers=1, expected_sha256='wrong')

    def test_instance_paths_are_separate_and_missing_placements_fail(self):
        doc = CadDocument.__new__(CadDocument)
        doc._closed = False
        doc.model = SimpleNamespace(children={1: [(10, 2), (11, 2)], 2: [(12, 3)]})
        doc._transforms = {n: np.eye(4) for n in (10, 11, 12)}
        self.assertEqual([path for _, _, path in doc.subtree(1)],
                         [(), (10,), (10, 12), (11,), (11, 12)])
        doc._transforms = {}
        with self.assertRaisesRegex(ValueError, 'explicit placement'):
            list(doc.subtree(1))

    def test_native_working_model_is_lazy_reused_and_keeps_source_separate(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone
        from export_step_elements import shape_counts
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'box.step'
            writer = STEPControl_Writer()
            writer.Transfer(BRepPrimAPI_MakeBox(10, 20, 30).Shape(), STEPControl_AsIs)
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            with CadDocument.from_step(path, workers=1) as document:
                working = document.working_model()
                self.assertIs(working, document.working_model())
                self.assertEqual(list(shape_counts(working.document)), [1, 6])
                for mode in ('Color', 'Name', 'Layer', 'Props', 'Mat'):
                    self.assertTrue(working.available_metadata_modes[mode])
                document.verify_source()

    def test_node_provenance_keeps_mesh_sharing_and_binary_exact(self):
        p = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0]])
        t = np.array([[0, 1, 2]])
        a, b = [GlbWriter('root', {'version': '2.0'}) for _ in range(2)]
        extra = {'cad_source': {'product_id': 1, 'relative_occurrence_path': [10]}}
        for writer in (a, b):
            for i in range(2):
                writer.add_node(str(i), p, t, ['1,0,0'], extras=extra if writer is b else None)
        extra['cad_source']['relative_occurrence_path'].append(999)
        self.assertEqual(bytes(a.bin), bytes(b.bin))
        self.assertEqual(a.meshes, b.meshes)
        self.assertEqual(len(b.meshes), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'mesh.glb'
            b.write(path)
            self.assertEqual(len(next(read_glb_local_nodes(path))), 5)
            records = list(read_glb_local_nodes(path, include_extras=True))
            self.assertEqual(records[0][5]['cad_source']['relative_occurrence_path'], [10])
            d, _ = read_glb(path)
            self.assertEqual(d['nodes'][1]['mesh'], d['nodes'][2]['mesh'])


if __name__ == '__main__':
    unittest.main()
