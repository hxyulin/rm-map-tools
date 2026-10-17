# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Native-generated fixtures check source-graph opening/hardware discovery."""
import hashlib,re,tempfile,unittest
from pathlib import Path
from cad_document import CadDocument
from cad_mounting_details import AnalyticDetails,mounting_details
from audit_cad_passes import PASSES,run_document


class MountingDetailTests(unittest.TestCase):
    def fixture(self,path,*,hole_radius=2,slot=False):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.gp import gp_Ax2,gp_Pnt,gp_Dir
        from OCP.BRep import BRep_Builder
        from OCP.TopoDS import TopoDS_Compound
        from OCP.STEPControl import STEPControl_Writer,STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone
        plate=BRepPrimAPI_MakeBox(100,100,5).Shape();drill=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(50,50,-1),gp_Dir(0,0,1)),hole_radius,7).Shape();
        if slot:
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
            second=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(60,50,-1),gp_Dir(0,0,1)),hole_radius,7).Shape();bridge=BRepPrimAPI_MakeBox(gp_Pnt(50,50-hole_radius,-1),10,2*hole_radius,7).Shape();drill=BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(drill,second).Shape(),bridge).Shape()
        plate=BRepAlgoAPI_Cut(plate,drill).Shape();shaft=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(150,0,0),gp_Dir(0,0,1)),4,12).Shape();large=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(200,0,0),gp_Dir(0,0,1)),30,12).Shape()
        compound=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(compound)
        for shape in [plate,shaft,large]:builder.Add(compound,shape)
        writer=STEPControl_Writer();writer.Transfer(compound,STEPControl_AsIs);self.assertEqual(writer.Write(str(path)),IFSelect_RetDone)
        # This controlled fixture has exporter-ordered outer loops; make that
        # information explicit. The audit itself must not infer first=outer.
        text=path.read_text();outer=re.findall(r'ADVANCED_FACE\(.*?\(\s*#(\d+)',text)
        for bound in outer:text=re.sub(r'(#'+bound+r'\s*=\s*)FACE_BOUND',r'\1FACE_OUTER_BOUND',text)
        path.write_text(text)

    def test_hole_mouths_are_not_physical_hole_count_and_small_cylinder_is_unconfirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.step';self.fixture(path);before=hashlib.sha256(path.read_bytes()).hexdigest()
            with CadDocument.from_step(path,workers=1) as document:
                report=mounting_details(document)
                self.assertEqual(report['circular_opening_mouths'],2);self.assertEqual(len(report['coaxial_opening_families']),1)
                self.assertEqual(report['possible_fastener_units'],1);candidate=report['fasteners'][0]
                self.assertEqual(candidate['transverse_span_upper_bound_mm'],8);self.assertEqual(candidate['axial_span_upper_bound_mm'],12);self.assertFalse(candidate['source_name_hint']);self.assertIn('unconfirmed',candidate['semantic_status'])
                self.assertTrue(all(r['source_body_ids'] and r['source_edge_ids'] for r in report['openings']))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_diameter_boundary_is_strict_and_registry_is_read_only(self):
        self.assertEqual(PASSES['mounting-details']['effect'],'read-only')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.step';self.fixture(path,hole_radius=8.5)
            with CadDocument.from_step(path,workers=1) as document:
                self.assertEqual(mounting_details(document)['opening_mouths'],0)
                result=run_document(document,['mounting-details']);self.assertEqual(result['actions'],[]);self.assertTrue(result['source_unchanged'])
                with self.assertRaises(ValueError):mounting_details(document,maximum_diameter_mm=float('nan'))

    def test_narrow_slot_and_length_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.step';self.fixture(path,slot=True)
            with CadDocument.from_step(path,workers=1) as document:
                result=mounting_details(document);self.assertEqual(result['narrow_noncircular_opening_mouths'],2)
                self.assertEqual(mounting_details(document,maximum_slot_length_mm=10)['opening_mouths'],0)

    def test_ambiguous_outer_topology_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.step';self.fixture(path);path.write_text(path.read_text().replace('FACE_OUTER_BOUND','FACE_BOUND'))
            with CadDocument.from_step(path,workers=1) as document:
                result=mounting_details(document);self.assertEqual(result['opening_mouths'],0);self.assertGreater(result['opening_skips']['ambiguous planar outer bound'],0)

    def test_split_circle_and_backtracking_are_distinguished(self):
        records="""#1=CARTESIAN_POINT('',(0.,0.,0.));
#2=DIRECTION('',(0.,0.,1.));
#3=DIRECTION('',(1.,0.,0.));
#4=AXIS2_PLACEMENT_3D('',#1,$,#3);
#5=CIRCLE('',#4,2.);
#6=CARTESIAN_POINT('',(2.,0.,0.));
#7=CARTESIAN_POINT('',(-2.,0.,0.));
#8=VERTEX_POINT('',#6);
#9=VERTEX_POINT('',#7);
#10=EDGE_CURVE('',#8,#9,#5,.T.);
#11=EDGE_CURVE('',#9,#8,#5,.T.);
#12=ORIENTED_EDGE('',*,*,#10,.T.);
#13=ORIENTED_EDGE('',*,*,#11,.T.);
#14=EDGE_LOOP('',(#12,#13));"""
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.step'
            for backtrack in [False,True]:
                text=records.replace("#11=EDGE_CURVE('',#9,#8,#5,.T.);","#11=EDGE_CURVE('',#9,#8,#5,.F.);") if backtrack else records
                path.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n"+text+"\nENDSEC;\nEND-ISO-10303-21;\n")
                with CadDocument.from_step(path,workers=1) as document:
                    circle=AnalyticDetails(document).loop(14)[2]
                    if backtrack:self.assertIsNone(circle)
                    else:self.assertAlmostEqual(circle[2],2)

    def test_output_refusal_and_units(self):
        from types import SimpleNamespace
        from audit_mounting_details import audit
        with self.assertRaises(ValueError):mounting_details(SimpleNamespace(geometry_length_units=['inch']))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.json';path.write_text('preserve')
            with self.assertRaises(FileExistsError):audit(Path('missing.step'),path,source_sha256='unused')
            self.assertEqual(path.read_text(),'preserve')

if __name__=='__main__':unittest.main()
