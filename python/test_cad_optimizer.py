# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Optimizer sharing retains identity, incidence, exact values and parameterization."""
from decimal import localcontext
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from cad_document import CadDocument
from cad_optimizer import (build_pool, build_optimizer_ir, decimal_key, direction_record,
                           factor_analytic_frames, factor_affine_primitives, unit_profile)
from test_p21model import FIXTURE
from test_cad_share_values import UNITS

RECORDS = """#100=CARTESIAN_POINT('first #999',(1.,2.,3.));
#101=CARTESIAN_POINT('second',(1.0,2E0,3.000));
#102=VERTEX_POINT('first vertex',#100);
#103=VERTEX_POINT('second vertex',#101);
#104=DIRECTION('first direction',(2.,0.,0.));
#105=DIRECTION('second direction',(1.,0.,0.));
#106=DIRECTION('',(-1.,0.,0.));
#107=DIRECTION('',(0.5,0.5,0.));
#108=DIRECTION('',(1.,1.,0.));
#110=AXIS2_PLACEMENT_3D('',#100,#104,#107);
#111=AXIS2_PLACEMENT_3D('',#200,#105,#108);
#120=CIRCLE('first circle',#110,5.);
#121=CIRCLE('second circle',#111,5E0);
#122=CIRCLE('integer radius',#111,5);
#123=CIRCLE('near radius',#111,5.000000000000001);
#124=CYLINDRICAL_SURFACE('',#110,5.);
#125=SPHERICAL_SURFACE('',#110,5.);
#126=ELLIPSE('',#110,5.,3.);
#140=LINE('',#100,#150);
#141=LINE('',#200,#151);
#150=VECTOR('',#104,2.);
#151=VECTOR('',#105,9.);
#180=OPAQUE('literal #100 1E4',"01AE",1.00,.T.,#100);
#181=OPAQUE('different label',"01AE",1.00,.T.,#100);
#200=CARTESIAN_POINT('',(100.,200.,300.));
"""


class OptimizerTests(unittest.TestCase):
    def fixture(self, root, extra=RECORDS, units=UNITS):
        source=root/'source.step'
        source.write_text(FIXTURE.replace('ENDSEC;\nEND-ISO-10303-21;', extra+units+'ENDSEC;\nEND-ISO-10303-21;'))
        return source

    def test_decimal_normalization_has_no_float_or_decimal_context_rounding(self):
        self.assertEqual(decimal_key(b'1.0000'),decimal_key(b'100E-2'))
        self.assertNotEqual(decimal_key(b'1'),decimal_key(b'1.0'))
        self.assertNotEqual(decimal_key(b'-0.'),decimal_key(b'0.'))
        self.assertNotEqual(decimal_key(b'1.000000000000001'),decimal_key(b'1.'))
        literal=b'123456789012345678901234567890.123456789'
        with localcontext() as context:
            context.prec=1
            self.assertIn(b'123456789012345678901234567890123456789',decimal_key(literal))
        with self.assertRaises(ValueError):decimal_key(b'.T.')

    def test_shared_recipes_keep_original_vertex_identity_and_incidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with CadDocument.from_step(self.fixture(Path(tmp)),intern_layers=True) as doc:
                rows=[doc.index.r(v) for v in (102,103,180,181)]
                pool=build_pool(doc,rows,decimals=True,display_names=True)
                self.assertEqual(pool.recipe_for_source(102),pool.recipe_for_source(103))
                self.assertEqual(pool.source_children(102).tolist(),[100])
                self.assertEqual(pool.source_children(103).tolist(),[101])
                self.assertEqual(doc.entity(100).strings,('first #999',))
                self.assertNotEqual(pool.recipe_for_source(180),pool.recipe_for_source(181))
                record=pool.record(pool.recipe_for_source(180))
                self.assertIn(b"'literal #100 1E4'",record)
                self.assertIn(b'"01AE"',record)
                self.assertIn(b'.T.',record)
                self.assertGreater(pool.validate(),0)
                with self.assertRaises(ValueError):pool.source_to_recipe[0]=0
                with self.assertRaisesRegex(ValueError,'outside'):pool.recipe_for_source(1)
            with self.assertRaisesRegex(ValueError,'closed'):pool.source_children(102)

    def test_direction_ratios_normalize_positive_scale_only(self):
        self.assertEqual(direction_record(b"DIRECTION('',(2.,0.,0.));"),direction_record(b"DIRECTION('',(1.,0.,0.));"))
        self.assertEqual(direction_record(b"DIRECTION('',(.5,.5,0.));"),direction_record(b"DIRECTION('',(1.,1.,0.));"))
        self.assertNotEqual(direction_record(b"DIRECTION('',(-1.,0.,0.));"),direction_record(b"DIRECTION('',(1.,0.,0.));"))
        self.assertIsNone(direction_record(b"DIRECTION('',(1E1000,1E-1000));"))
        with self.assertRaisesRegex(ValueError,'zero'):direction_record(b"DIRECTION('',(0.,0.,0.));")
        with tempfile.TemporaryDirectory() as tmp:
            with CadDocument.from_step(self.fixture(Path(tmp))) as doc:
                pool=build_pool(doc,[doc.index.r(v) for v in (104,105,106,107,108)],decimals=False,display_names=True,directions=True)
                self.assertEqual(pool.recipe_for_source(104),pool.recipe_for_source(105))
                self.assertEqual(pool.recipe_for_source(107),pool.recipe_for_source(108))
                self.assertNotEqual(pool.recipe_for_source(105),pool.recipe_for_source(106))
                pool.validate()

    def test_analytic_profiles_keep_frames_trims_and_line_magnitudes_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            with CadDocument.from_step(self.fixture(Path(tmp))) as doc:
                pool=build_pool(doc,[doc.index.r(v) for v in (120,121,122,123,140,141)],decimals=False,display_names=True)
                catalog=factor_analytic_frames(pool)
                self.assertEqual(catalog.use(120).prototype,catalog.use(121).prototype)
                self.assertEqual(catalog.use(121).prototype,catalog.use(122).prototype)
                self.assertNotEqual(catalog.use(122).prototype,catalog.use(123).prototype)
                self.assertEqual(catalog.use(120).frame_source_ids,(110,))
                self.assertEqual(catalog.use(121).frame_source_ids,(111,))
                self.assertEqual(catalog.use(140).prototype,catalog.use(141).prototype)
                self.assertEqual(catalog.use(140).frame_source_ids,(100,150))
                self.assertEqual(catalog.use(141).frame_source_ids,(200,151))
                self.assertIn(b'2.',doc.entity(150).raw)
                self.assertIn(b'9.',doc.entity(151).raw)
                self.assertFalse(catalog.skipped)
                self.assertFalse(catalog.uses.flags.writeable)

    def test_unit_analytic_shapes_preserve_exact_scales_and_native_parameters(self):
        from OCP.Geom import Geom_Circle, Geom_Ellipse, Geom_CylindricalSurface, Geom_SphericalSurface
        from OCP.gp import gp_Ax2, gp_Ax3
        with tempfile.TemporaryDirectory() as tmp:
            with CadDocument.from_step(self.fixture(Path(tmp))) as doc:
                pool=build_pool(doc,[doc.index.r(v) for v in (120,123,124,125,126)],decimals=False,display_names=True)
                affine=factor_affine_primitives(factor_analytic_frames(pool))
                self.assertEqual(affine.use(120).prototype,affine.use(123).prototype)
                self.assertNotEqual(affine.use(120).local_scale,affine.use(123).local_scale)
                self.assertEqual(affine.use(124).local_scale,('~R5E0','~R5E0','~R1E0'))
                self.assertEqual(affine.use(125).local_scale,('~R5E0',)*3)
                self.assertEqual(affine.use(126).local_scale,('~R5E0','~R3E0','~R1E0'))
                # Independent kernel point evaluations verify the local maps,
                # especially cylinder's unchanged axial v coordinate.
                cases=[(120,Geom_Circle(gp_Ax2(),5.),Geom_Circle(gp_Ax2(),1.),(0.73,)),
                       (124,Geom_CylindricalSurface(gp_Ax3(),5.),Geom_CylindricalSurface(gp_Ax3(),1.),(0.73,7.2)),
                       (125,Geom_SphericalSurface(gp_Ax3(),5.),Geom_SphericalSurface(gp_Ax3(),1.),(0.73,0.31)),
                       (126,Geom_Ellipse(gp_Ax2(),5.,3.),Geom_Circle(gp_Ax2(),1.),(0.73,))]
                for source,original,unit,args in cases:
                    scale=np.array([float(v[2:]) for v in affine.use(source).local_scale])
                    expected=np.array(original.Value(*args).Coord())
                    actual=np.array(unit.Value(*args).Coord())*scale
                    np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-13)

    def test_cycles_missing_refs_mixed_units_and_wrong_catalog_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for records,error in [("#500=VERTEX_POINT('',#501);\n#501=VERTEX_POINT('',#500);\n",'cyclic'),
                                  ("#500=VERTEX_POINT('',#9999);\n",'unresolved')]:
                with CadDocument.from_step(self.fixture(root,extra=records)) as doc:
                    with self.assertRaisesRegex(ValueError,error):
                        build_pool(doc,[doc.index.r(500)],decimals=False,display_names=True)
            more="\n#910=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT($,.METRE.));\n#911=(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNIT_ASSIGNED_CONTEXT((#910))REPRESENTATION_CONTEXT('',''));\n"
            with CadDocument.from_step(self.fixture(root,units=UNITS+more)) as doc:
                with self.assertRaisesRegex(ValueError,'unit profile'):unit_profile(doc)
            catalog=root/'hierarchy.json';catalog.write_text(json.dumps({'files_sha256':{'field.step':'wrong'}}))
            with CadDocument.from_step(self.fixture(root)) as doc:
                with self.assertRaisesRegex(ValueError,'catalog'):build_optimizer_ir(doc,hierarchy=catalog)


if __name__=='__main__':unittest.main()
