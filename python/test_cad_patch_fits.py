# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Finite patches retain trim/incidence; approximate fits report actual errors."""
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

import numpy as np
from cad_document import CadDocument
from cad_patch_matching import polygon_patch,patch_key,patch_correspondence
from cad_shape_fitting import (rectangle_fit,polygon_fits,simplify_polygon,
                              fit_round_profiles,fit_wave_profiles,bspline_samples,native_spline_sample_error)
from test_p21model import FIXTURE
from test_cad_share_values import UNITS


def polygon_records(base,points,start=0):
    rows=[];uses=[]
    for i,p in enumerate(points):
        a=base+i*10;b=base+((i+1)%len(points))*10
        delta=[float(Fraction(str(b))-Fraction(str(a))) for a,b in zip(p,points[(i+1)%len(points)])]
        coordinates=','.join(str(float(v)) for v in p)
        direction=','.join(str(float(v)) for v in delta)
        rows += [f"#{a}=CARTESIAN_POINT('',({coordinates}));",f"#{a+1}=VERTEX_POINT('',#{a});",
                 f"#{a+2}=DIRECTION('',({direction}));",f"#{a+3}=VECTOR('',#{a+2},1.);",
                 f"#{a+4}=LINE('',#{a},#{a+3});",f"#{a+5}=EDGE_CURVE('',#{a+1},#{b+1},#{a+4},.T.);",
                 f"#{a+6}=ORIENTED_EDGE('',*,*,#{a+5},.T.);"]
        uses.append(a+6)
    uses=uses[start:]+uses[:start]
    n=base+len(points)*10
    rows += [f"#{n}=EDGE_LOOP('',({','.join('#'+str(v) for v in uses)}));",
             f"#{n+1}=FACE_OUTER_BOUND('',#{n},.T.);",f"#{n+2}=DIRECTION('',(0.,0.,1.));",
             f"#{n+3}=AXIS2_PLACEMENT_3D('',#{base},#{n+2},$);",f"#{n+4}=PLANE('',#{n+3});",
             f"#{n+5}=ADVANCED_FACE('',(#{n+1}),#{n+4},.T.);"]
    return '\n'.join(rows)+'\n',n+5


class PatchFitTests(unittest.TestCase):
    def source(self,root,records):
        path=root/'source.step';path.write_text(FIXTURE.replace('ENDSEC;\nEND-ISO-10303-21;',records+UNITS+'ENDSEC;\nEND-ISO-10303-21;'));return path

    def test_finite_patch_rigid_congruence_cyclic_start_and_explicit_maps(self):
        a,fa=polygon_records(100,[[0,0,0],[4,0,0],[4,2,0],[0,2,0]])
        b,fb=polygon_records(200,[[10,20,0],[10,24,0],[8,24,0],[8,20,0]],2)
        c,fc=polygon_records(300,[[0,0,0],[4,0,0],[4,2,0],[0,2.001,0]])
        with tempfile.TemporaryDirectory() as tmp, CadDocument.from_step(self.source(Path(tmp),a+b+c)) as doc:
            first=polygon_patch(doc,fa);second=polygon_patch(doc,fb);near=polygon_patch(doc,fc)
            self.assertEqual(patch_key(first)[0],patch_key(second)[0])
            self.assertNotEqual(patch_key(first)[0],patch_key(near)[0])
            proof=patch_correspondence(first,second)
            self.assertLess(proof['max_vertex_residual_source_units'],1e-12)
            self.assertEqual(len(proof['correspondence']['vertex_ids']),4)
            with self.assertRaisesRegex(ValueError,'different finite'):patch_correspondence(first,near)
            proposal=patch_correspondence(first,near,quantum=.01)
            self.assertIn('no reuse authorized',proposal['acceptance'])
            self.assertGreater(proposal['max_vertex_residual_source_units'],0)
            with self.assertRaises(ValueError):patch_key(first,quantum=-1)
            # Source endpoint on the wrong underlying line must not pass exact mode.
            from dataclasses import replace
            with self.assertRaises(ValueError):patch_key(replace(first,points=(first.points[1],)+first.points[1:]))

    def test_holes_and_disconnected_trim_are_refused(self):
        a,fa=polygon_records(100,[[0,0,0],[4,0,0],[4,2,0],[0,2,0]])
        a=a.replace("(#141),#144","(#141,#141),#144")
        with tempfile.TemporaryDirectory() as tmp, CadDocument.from_step(self.source(Path(tmp),a)) as doc:
            with self.assertRaisesRegex(ValueError,'bounds'):polygon_patch(doc,fa)
        a,fa=polygon_records(100,[[0,0,0],[4,0,0],[4,2,0],[0,2,0]])
        a=a.replace('#111,#104','#121,#104')
        with tempfile.TemporaryDirectory() as tmp, CadDocument.from_step(self.source(Path(tmp),a)) as doc:
            with self.assertRaisesRegex(ValueError,'disconnected'):polygon_patch(doc,fa)

    def test_self_intersections_and_zero_length_edges_fail_closed(self):
        a,fa=polygon_records(100,[[0,0,0],[4,2,0],[0,3,0],[4,0,0]])
        with tempfile.TemporaryDirectory() as tmp, CadDocument.from_step(self.source(Path(tmp),a)) as doc:
            with self.assertRaisesRegex(ValueError,'self-intersecting'):patch_key(polygon_patch(doc,fa))
        a,fa=polygon_records(100,[[0,0,0],[4,0,0],[4,0,0],[0,2,0]])
        with tempfile.TemporaryDirectory() as tmp, CadDocument.from_step(self.source(Path(tmp),a)) as doc:
            with self.assertRaisesRegex(ValueError,'zero-length'):polygon_patch(doc,fa)

    def test_rectangles_triangles_and_continuous_boundary_bounds(self):
        p=np.array([[0.,0,0],[2,0,0],[4,.01,0],[4,2,0],[0,2,0]])
        reduced,report=simplify_polygon(p,.02)
        self.assertEqual(len(reduced),4)
        self.assertLessEqual(report['continuous_chain_error_bound_source_units'],.02)
        proposal=polygon_fits(p,.02)['models'][0]
        fitted=np.array(proposal['corners'])
        edges=np.roll(fitted,-1,axis=0)-fitted
        self.assertLess(abs(edges[0]@edges[1]),1e-10)
        self.assertLess(proposal['continuous_boundary_error_bound_source_units'],.05)
        def sampled_boundary(poly):
            return np.concatenate([a+(b-a)*np.linspace(0,1,101)[:,None]
                                   for a,b in zip(poly,np.roll(poly,-1,axis=0))])
        def distances(samples,poly):
            result=[]
            for a,b in zip(poly,np.roll(poly,-1,axis=0)):
                delta=b-a;t=np.clip((samples-a)@delta/(delta@delta),0,1)
                result.append(np.linalg.norm(samples-(a+t[:,None]*delta),axis=1))
            return np.min(result,axis=0)
        bound=proposal['continuous_boundary_error_bound_source_units']
        self.assertLessEqual(float(distances(sampled_boundary(p),fitted).max()),bound+1e-12)
        self.assertLessEqual(float(distances(sampled_boundary(fitted),p).max()),bound+1e-12)

        triangle=polygon_fits([[0,0,0],[4,0,0],[.01,3,0]])['models']
        best=min((m for m in triangle if m['model']=='right_triangle'),key=lambda m:m['continuous_boundary_error_bound_source_units'])
        self.assertLess(best['continuous_boundary_error_bound_source_units'],.02)
        with self.assertRaises(ValueError):rectangle_fit([[0,0,0]]*4)

    def test_ellipse_and_line_fits_use_held_out_geometric_distances(self):
        t=np.linspace(0,2*np.pi,65);v=np.linspace(0,2*np.pi,257)
        points=lambda q:np.column_stack((4*np.cos(q),2*np.sin(q),np.zeros(len(q))))
        models=fit_round_profiles(points(t),points(v));by_kind={m['model']:m for m in models}
        self.assertLess(by_kind['ellipse']['max_sample_error_source_units'],1e-6)
        self.assertGreater(by_kind['circle']['max_sample_error_source_units'],.5)
        training=np.column_stack((t,2*t,np.zeros(len(t))))
        models=fit_round_profiles(training,training)
        self.assertLess(models[0]['max_sample_error_source_units'],1e-12)

    def test_sine_and_semicircular_profiles_are_compared(self):
        t=np.linspace(0,100,129);v=np.linspace(0,100,1025)
        sine=lambda x:np.column_stack((x,3*np.sin(2*np.pi*x/20),np.zeros(len(x))))
        models=fit_wave_profiles(sine(t),sine(v));sine_fit=next(m for m in models if m['model']=='sinusoid')
        self.assertLess(sine_fit['max_sample_error_source_units'],1e-5)
        arch=lambda x:np.column_stack((x,10*np.sqrt(np.maximum(0,1-(2*((x/20)%1)-1)**2)),np.zeros(len(x))))
        models=fit_wave_profiles(arch(t),arch(v));arch_fit=next(m for m in models if m['model']=='semiellipse_train')
        self.assertLess(arch_fit['max_sample_error_source_units'],.05)
        self.assertLess(abs(arch_fit['parameters']['height_to_half_period_ratio']-1),.01)
        # A loop cannot be treated as a single-valued wave profile.
        loop=np.column_stack((np.cos(t),np.sin(t),np.zeros(len(t))))
        self.assertEqual(fit_wave_profiles(loop,loop),[])

    def test_bspline_sampling_matches_independent_occt_evaluation(self):
        records="""#100=CARTESIAN_POINT('',(0.,0.,0.));
#101=CARTESIAN_POINT('',(1.,2.,0.));
#102=CARTESIAN_POINT('',(2.,0.,0.));
#103=VERTEX_POINT('',#100);
#104=VERTEX_POINT('',#102);
#105=B_SPLINE_CURVE_WITH_KNOTS('',2,(#100,#101,#102),.UNSPECIFIED.,.F.,.F.,(3,3),(0.,1.),.UNSPECIFIED.);
#106=EDGE_CURVE('',#103,#104,#105,.T.);
"""
        with tempfile.TemporaryDirectory() as tmp, CadDocument.from_step(self.source(Path(tmp),records)) as doc:
            samples=bspline_samples(doc,106,33)
            self.assertLess(native_spline_sample_error(doc,106,samples),1e-12)
            from OCP.Geom import Geom_BezierCurve
            from OCP.collections import Array1_gp_Pnt as TColgp_Array1OfPnt
            from OCP.gp import gp_Pnt
            controls=TColgp_Array1OfPnt(1,3)
            for i,p in enumerate(((0,0,0),(1,2,0),(2,0,0)),1):controls.SetValue(i,gp_Pnt(*p))
            curve=Geom_BezierCurve(controls)
            expected=np.array([curve.Value(float(t)).Coord() for t in np.linspace(0,1,33)])
            self.assertTrue(np.allclose(samples,expected,atol=1e-13,rtol=0))

    def test_audit_source_qualified_groups_and_no_mutation(self):
        import hashlib
        from audit_patch_fits import audit
        a,fa=polygon_records(100,[[0,0,0],[4,0,0],[4,2,0],[0,2,0]])
        b,fb=polygon_records(200,[[10,20,0],[10,24,0],[8,24,0],[8,20,0]],2)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=self.source(root,a+b)
            source.write_text(source.read_text().replace("#7=OPEN_SHELL('',(#8));",f"#7=OPEN_SHELL('',(#{fa},#{fb}));"))
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            report=audit(source,root/'report.json',curve_limit=0)
            self.assertEqual(report['supported_polygon_faces'],2)
            self.assertEqual(report['exact_finite_patch_groups']['additional_face_uses'],1)
            self.assertEqual(report['source_sha256'],digest)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
            with self.assertRaises(FileExistsError):audit(source,root/'report.json')
            from cad_optimizer import build_optimizer_ir
            with CadDocument.from_step(source) as doc:
                self.assertEqual(build_optimizer_ir(doc).polygon_patch(fa).face_id,fa)


if __name__=='__main__':unittest.main()
