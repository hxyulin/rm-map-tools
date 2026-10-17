# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Native mounting previews retain exact untouched geometry and source face paint."""
import tempfile,unittest
from pathlib import Path
import numpy as np
import test_cad_mounting_details as fixtures
from cad_document import CadDocument
from cad_mounting_details import mounting_details
from cad_mounting_preview import bind_details,preview_mesh
from validate_parts import read_part
from cad_wall_fill import shape_map
from mesh_parts import tessellate
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool,XCAFDoc_ColorSurf
from OCP.collections import Sequence_TDF_Label

class MountingPreviewTests(unittest.TestCase):
    def prepare(self,path,paint=False):
        native,reader,error=read_part(str(path));self.assertIsNone(error);roots=Sequence_TDF_Label();tool=XCAFDoc_DocumentTool.ShapeTool_s(native.Main());tool.GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE)
        if paint:
            from OCP.Quantity import Quantity_Color,Quantity_TOC_sRGB
            from OCP.TDocStd import TDocStd_Document
            from OCP.TCollection import TCollection_ExtendedString
            native=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'));label=XCAFDoc_DocumentTool.ShapeTool_s(native.Main()).AddShape(root,False);XCAFDoc_DocumentTool.ColorTool_s(native.Main()).SetColor(label,Quantity_Color(.3412,.3098,.1608,Quantity_TOC_sRGB),XCAFDoc_ColorSurf)
        owners=[];p,t,m,palette=tessellate(native,.4,.6,{},lambda i,f,n:owners.extend([faces.FindIndex(f)]*n));return native,reader,root,p,t,m,palette,np.array(owners)

    def test_variants_retain_exact_unselected_triangles(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.step';fixtures.MountingDetailTests().fixture(source);original=source.read_bytes();native,reader,root,p,t,m,palette,owners=self.prepare(source)
            with CadDocument.from_step(source,workers=1) as doc:
                f=mounting_details(doc);bindings=bind_details(doc,root,f['openings'],f['fasteners'])
                self.assertEqual(bindings['proof']['matched_source_opening_mouths'],2);self.assertEqual(bindings['proof']['withheld_source_fastener_unit_ids'],[])
                self.assertEqual(len(bindings['dropped']),3)
                for fill,remove in [(False,False),(True,False),(False,True),(True,True)]:
                    pp,tt,mm,ff,proof=preview_mesh(p,t,m,palette,owners,bindings,fill_holes=fill,remove_fasteners=remove);ids=np.array(proof['unchanged_input_triangle_indices']);np.testing.assert_array_equal(pp[tt[:len(ids)]],p[t[ids]]);np.testing.assert_array_equal(mm[:len(ids)],m[ids]);self.assertEqual(len(proof['rebuilt_faces']),2 if fill else 0)
            self.assertEqual(source.read_bytes(),original)

    def test_rebuilt_faces_keep_actual_resolved_native_paint(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.step';fixtures.MountingDetailTests().fixture(source);native,reader,root,p,t,m,palette,owners=self.prepare(source,paint=True)
            with CadDocument.from_step(source,workers=1) as doc:
                f=mounting_details(doc);bindings=bind_details(doc,root,f['openings'],[]);pp,tt,mm,ff,proof=preview_mesh(p,t,m,palette,owners,bindings,fill_holes=True)
            self.assertTrue(proof['rebuilt_faces']);self.assertTrue(all(v['source_colour']=='0.3412,0.3098,0.1608' for v in proof['rebuilt_faces']));self.assertEqual({palette[k] for k in mm},{'0.3412,0.3098,0.1608'})

    def test_unmatched_source_hardware_is_withheld(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.step';fixtures.MountingDetailTests().fixture(source);native,reader,root,p,t,m,palette,owners=self.prepare(source)
            with CadDocument.from_step(source,workers=1) as doc:
                f=mounting_details(doc);entry=dict(f['fasteners'][0]);entry['axis_origin_mm']=[99999,99999,99999];bindings=bind_details(doc,root,[],[entry]);self.assertFalse(bindings['dropped']);self.assertEqual(bindings['proof']['withheld_source_fastener_unit_ids'],[entry['source_unit_id']])
if __name__=='__main__':unittest.main()
