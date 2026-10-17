# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Continuous bounds, finite seams, automatic thresholds and portable vectors."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from cad_vector_ir import (FitPolicy,VectorCurve,VectorIR,VectorUse,certify_fit,
                           fitted_curve,source_spline,build_vector_ir,RuledSurface,vector_polygon)
from cad_document import CadDocument
from test_p21model import FIXTURE
from test_cad_share_values import UNITS


def quadratic(height):
    return VectorCurve.make('source-bspline',{'degree':2,'control_points':[['0','0','0'],['0.5',str(height),'0'],['1','0','0']],
        'knots':['0','1'],'multiplicities':[3,3],'reverse':False})


class VectorTests(unittest.TestCase):
    def test_policy_and_feature_scale(self):
        policy=FitPolicy()
        self.assertEqual(policy.budget(1000),.25)
        self.assertEqual(policy.budget(.1),.0005)
        for args in ({'max_error_mm':float('nan')},{'feature_fraction':0},{'feature_fraction':1},{'max_intervals':1}):
            with self.assertRaises(ValueError):FitPolicy(**args)
        source=quadratic(.002);line=VectorCurve.make('line',{'endpoints_mm':[[0,0,0],[1,0,0]]})
        mapping=lambda points:points[:,0]
        self.assertFalse(certify_fit(source,line,mapping,policy,.1)['accepted'])
        proof=certify_fit(source,line,mapping,policy,100)
        self.assertTrue(proof['accepted'])
        self.assertGreaterEqual(proof['continuous_error_bound_mm'],.001)

    def test_line_endpoints_survive_floating_cancellation(self):
        points=[[1000000.,0,0],[.00001,0,0]]
        curve=VectorCurve.make('line',{'endpoints_mm':points})
        self.assertTrue(np.array_equal(curve.evaluator().value([0,1]),points))

    def test_tessellation_catches_waves_with_flat_midpoints(self):
        curve=VectorCurve.make('sinusoid',{'origin_mm':[0,0,0],'axes_rows':[[1,0,0],[0,1,0]],'length_mm':100,
            'period_mm':20,'coefficients':[0,0,3,0],'endpoints_mm':[[0,0,0],[100,0,0]],'endpoint_corrections_mm':[[0,0,0],[0,0,0]]})
        evaluator=curve.evaluator();parameters,points,bound=evaluator.tessellate(.001)
        self.assertGreater(len(points),100)
        dense=np.linspace(0,1,10001);actual=evaluator.value(dense)
        linear=np.column_stack([np.interp(dense,parameters,points[:,axis]) for axis in range(3)])
        self.assertLessEqual(float(np.linalg.norm(actual-linear,axis=1).max()),bound+1e-10)
        with self.assertRaisesRegex(ValueError,'segment limit'):evaluator.tessellate(.00001,max_segments=10)

    def test_continuous_certificate_rejects_narrow_spline_peak(self):
        knots=[0,0,0,.4999,.5,.5001,1,1,1]
        controls=[[(knots[i+1]+knots[i+2])/2,y,0] for i,y in enumerate((0,0,1,1,0,0))]
        source=VectorCurve.make('source-bspline',{'degree':2,'control_points':controls,'knots':[0,.4999,.5,.5001,1],
            'multiplicities':[3,1,1,1,3],'reverse':False})
        line=VectorCurve.make('line',{'endpoints_mm':[[0,0,0],[1,0,0]]})
        proof=certify_fit(source,line,lambda points:points[:,0],FitPolicy(),100)
        self.assertFalse(proof['accepted'])
        parameters,points,bound=source.evaluator().tessellate(.001)
        self.assertGreater(float(points[:,1].max()),.5)
        self.assertTrue(all(any(abs(p-k)<1e-12 for p in parameters) for k in (.4999,.5,.5001)))

    def test_portable_readback_precision_fallback_and_shared_endpoints(self):
        source=quadratic(.002);line=VectorCurve.make('line',{'endpoints_mm':[[0,0,0],[1,0,0]]})
        proof=certify_fit(source,line,lambda points:points[:,0],FitPolicy(),100)
        use=VectorUse(10,20,(30,40),((0,0,0),(1,0,0)),True,1,0,('fixture',),json.dumps(proof).encode())
        layer=VectorIR('a'*64,FitPolicy(),(source,line),(use,))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'vectors.json';layer.write(path);loaded=VectorIR.read(path)
            coarse,c=loaded.export_curve(10,.1);fine,f=loaded.export_curve(10,.0001)
            self.assertFalse(c['source_fallback']);self.assertTrue(f['source_fallback'])
            self.assertGreater(len(fine),len(coarse))
            self.assertLessEqual(f['total_error_bound_mm'],.0001)
            self.assertEqual(coarse[[0,-1]].tolist(),[[0,0,0],[1,0,0]])
            self.assertEqual(fine[[0,-1]].tolist(),coarse[[0,-1]].tolist())
            from export_vector_selection import export
            output=Path(tmp)/'curves.json';summary=export(loaded,output,.0001)
            self.assertEqual(summary['curves'],1)
            data=json.loads(output.read_text())
            self.assertTrue(data['curves'][0]['source_fallback'])
            self.assertLessEqual(data['curves'][0]['total_error_bound_mm'],.0001)
            with self.assertRaises(FileExistsError):export(loaded,output,.0001)
            with self.assertRaises(FileExistsError):layer.write(path)
            data=json.loads(path.read_text());data['geometries'][1]['parameters']['endpoints_mm'][1][0]=2
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'checksum'):VectorIR.read(path)

    def test_spline_lexemes_and_pinned_ellipse_export(self):
        source=quadratic(.002)
        # Ellipse construction keeps a finite arc and exact shared endpoints,
        # even when the fitted circle is slightly displaced.
        model={'model':'ellipse','parameters':{'center_uv':[.5,0],'radii':[.5,.6],'angle_rad':0.},
               'plane_frame_source_units':{'origin':[0,0,0],'basis_rows':np.eye(3).tolist()}}
        arc,mapping,feature=fitted_curve(source,model,((0,0,0),(1,0,0)))
        self.assertTrue(np.array_equal(arc.evaluator().value([0,1]),[[0,0,0],[1,0,0]]))
        self.assertAlmostEqual(abs(arc.parameters['angle_span_rad']),np.pi)
        self.assertFalse(certify_fit(source,arc,mapping,FitPolicy(),feature)['accepted'])
        # A full-span Bezier source is used separately to check lexical retention.
        records="""#100=CARTESIAN_POINT('',(0.000,0.,0.));
#101=CARTESIAN_POINT('',(0.5000,0.00200,0.));
#102=CARTESIAN_POINT('',(1E0,0.,0.));
#103=VERTEX_POINT('',#100);
#104=VERTEX_POINT('',#102);
#105=B_SPLINE_CURVE_WITH_KNOTS('',2,(#100,#101,#102),.UNSPECIFIED.,.F.,.F.,(3,3),(0.000,1E0),.UNSPECIFIED.);
#106=EDGE_CURVE('',#103,#104,#105,.T.);
"""
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.step';path.write_text(FIXTURE.replace('ENDSEC;\nEND-ISO-10303-21;',records+UNITS+'ENDSEC;\nEND-ISO-10303-21;'))
            with CadDocument.from_step(path) as document:
                curve,vertices,endpoints,source_id=source_spline(document,106)
                self.assertEqual(curve.parameters['control_points'][0][0],'0.000')
                self.assertEqual(curve.parameters['knots'][1],'1E0')
                model={'model':'line','parameters':{}}
                layer=build_vector_ir(document,{'source_sha256':document.source_sha256,
                    'curve_examples':[{'source_edge_id':106,'components':['fixture'],'models':[model]}]})
                self.assertTrue(json.loads(layer.uses[0].decision)['accepted'])
                with self.assertRaisesRegex(ValueError,'source mismatch'):
                    build_vector_ir(document,{'source_sha256':'wrong','curve_examples':[]})

    def test_ruled_surface_tessellation_includes_saddle_twist(self):
        first=VectorCurve.make('line',{'endpoints_mm':[[0,0,0],[1,0,0]]})
        second=VectorCurve.make('line',{'endpoints_mm':[[0,1,0],[1,1,1]]})
        patch=RuledSurface(first,second)
        vertices,triangles,proof=patch.tessellate(.001)
        self.assertGreater(len(triangles),2)
        self.assertLessEqual(proof['surface_error_bound_mm'],.001)
        # At each strip center, bilinear-to-triangle displacement is twist/4.
        u=vertices[::2,0];mid=(u[:-1]+u[1:])/2
        actual=patch.value(mid,np.full(len(mid),.5))
        triangle_mid=(vertices[2:-1:2]+vertices[1:-2:2])/2
        self.assertLessEqual(float(np.linalg.norm(actual-triangle_mid,axis=1).max()),proof['surface_error_bound_mm']+1e-12)
        with self.assertRaisesRegex(ValueError,'segment limit'):patch.tessellate(.0001,max_segments=2)

    def test_polygon_vectors_retain_original_corners_and_tight_fallback(self):
        from test_cad_patch_fits import polygon_records
        examples=[([[0,0,0],[2,.001,0],[4,0,0],[4,2,0],[0,2,0]],True),
                  ([[0,0,0],[2,.001,0],[4,0,0],[4,.01,0],[0,.01,0]],False),
                  ([[0,0,0],[4,.001,0],[4,2,0],[0,2,0]],False)]
        for points,expected in examples:
            records,face=polygon_records(100,points)
            with tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'source.step';source.write_text(FIXTURE.replace('ENDSEC;\nEND-ISO-10303-21;',records+UNITS+'ENDSEC;\nEND-ISO-10303-21;'))
                with CadDocument.from_step(source) as document:
                    polygon=vector_polygon(document,face,FitPolicy())
                self.assertEqual(json.loads(polygon.decision)['accepted'],expected)
                layer=VectorIR('a'*64,FitPolicy(),(),(),(polygon,))
                path=Path(tmp)/'vectors.json';layer.write(path);reloaded=VectorIR.read(path)
                coarse,c=reloaded.polygons[0].outline(.1);fine,f=reloaded.polygons[0].outline(.0001)
                self.assertTrue(np.array_equal(fine,np.array(points)))
                if expected:
                    self.assertEqual(len(coarse),4);self.assertFalse(c['original_boundary_fallback'])
                    self.assertTrue(f['original_boundary_fallback'])
                    self.assertTrue(np.array_equal(coarse,np.array(points)[[0,2,3,4]]))


if __name__=='__main__':unittest.main()
