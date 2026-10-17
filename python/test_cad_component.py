# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Native component binding, shared topology and bounded prototype reuse."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from cad_vector_ir import VectorCurve
from cad_vector_cache import VectorCache,difference_bound
from cad_component import NativeComponent
from cad_component_mesh import vector_component_mesh,triangulate_polygon,orient_closed_mesh


class ComponentTests(unittest.TestCase):
    def test_translated_rotated_prototypes_and_quality_cache(self):
        p={'degree':2,'control_points':[[0,0,0],[5,3,0],[10,0,0]],'knots':[0,1],'multiplicities':[3,3],'reverse':False}
        first=VectorCurve.make('source-bspline',p);angle=.7
        rotation=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        changed={**p,'control_points':(np.array(p['control_points'])@rotation.T+[1234,-789,5]).tolist()}
        second=VectorCurve.make('source-bspline',changed);cache=VectorCache();a=cache.register(first);b=cache.register(second)
        self.assertEqual(a.prototype,b.prototype)
        t,aa,proof=cache.sample(a,.01);_,bb,_=cache.sample(b,.01)
        self.assertTrue(np.allclose(aa@rotation.T+[1234,-789,5],bb,atol=1e-7,rtol=0))
        dense=first.evaluator().value(t)
        self.assertLessEqual(float(np.linalg.norm(dense-aa,axis=1).max()),proof['curve_error_bound_mm'])
        self.assertEqual(cache.statistics()['tessellation_hits'],1)
        cache.sample(a,.001);self.assertEqual(cache.statistics()['tessellation_entries'],2)
        scaled=VectorCurve.make('source-bspline',{**p,'control_points':(np.array(p['control_points'])*2).tolist()})
        self.assertNotEqual(cache.register(scaled).prototype,a.prototype)

    def test_polynomial_comparison_catches_between_sample_difference_and_trims(self):
        p={'degree':2,'control_points':[[0,0,0],[.5,.1,0],[1,0,0]],'knots':[0,1],'multiplicities':[3,3],'reverse':False}
        a=VectorCurve.make('source-bspline',p);b=VectorCurve.make('source-bspline',{**p,'control_points':[[0,0,0],[.5,.1000002,0],[1,0,0]]})
        dense=np.linspace(0,1,1001);actual=float(np.linalg.norm(a.evaluator().value(dense)-b.evaluator().value(dense),axis=1).max())
        self.assertGreaterEqual(difference_bound(a,b)+1e-12,actual)
        trimmed=VectorCurve.make('source-bspline',{**p,'trim_parameters':[.2,.8]})
        self.assertTrue(np.allclose(trimmed.evaluator().value([0,1]),a.evaluator().value([.2,.8])))
        self.assertGreater(difference_bound(a,trimmed),.1)

    def test_nonplanar_mirror_is_not_a_rigid_prototype(self):
        p={'degree':3,'control_points':[[0,0,0],[1,1,1],[2,-1,2],[3,0,0]],'knots':[0,1],'multiplicities':[4,4],'reverse':False}
        mirror={**p,'control_points':(np.array(p['control_points'])*[1,1,-1]).tolist()}
        cache=VectorCache();a=cache.register(VectorCurve.make('source-bspline',p));b=cache.register(VectorCurve.make('source-bspline',mirror))
        self.assertNotEqual(a.prototype,b.prototype)

    def test_native_closed_box_keeps_source_topology_and_shared_samples(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.STEPControl import STEPControl_Writer,STEPControl_AsIs
        from OCP.IFSelect import IFSelect_RetDone
        from cad_document import CadDocument
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'box.step'
            from OCP.Interface import Interface_Static
            writer=STEPControl_Writer();previous=Interface_Static.IVal_s('write.surfacecurve.mode')
            try:
                Interface_Static.SetIVal_s('write.surfacecurve.mode',0)
                writer.Transfer(BRepPrimAPI_MakeBox(10,20,30).Shape(),STEPControl_AsIs)
                self.assertEqual(writer.Write(str(path)),IFSelect_RetDone)
            finally:Interface_Static.SetIVal_s('write.surfacecurve.mode',previous)
            with CadDocument.from_step(path,workers=1) as doc:body=int(doc.index.ids[doc.model.bodies[0][0]])
            with NativeComponent(path,body) as component:
                self.assertTrue(component.proof['source_native_incidence_verified'])
                points,triangles,faces,proof=vector_component_mesh(component,.1)
                self.assertEqual(len(triangles),12);self.assertEqual(len(set(faces)),6)
                self.assertAlmostEqual(proof['volume_mm3'],6000,places=5)
                self.assertEqual(proof['source_edges'],12)
                self.assertEqual(proof['shared_boundary_uses'],24)
                _,_,_,native=component.mesh(.1)
                self.assertEqual(native['shared_edge_cache_hits'],12)

    def test_extruded_curved_solid_caps_share_identical_boundaries(self):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
        from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
        from OCP.Geom import Geom_BezierCurve
        from OCP.collections import Array1_gp_Pnt
        from OCP.gp import gp_Pnt,gp_Vec
        from OCP.STEPControl import STEPControl_Writer,STEPControl_AsIs
        from OCP.Interface import Interface_Static
        from cad_document import CadDocument
        controls=Array1_gp_Pnt(1,3)
        for i,p in enumerate(((0,1,0),(5,3,0),(10,1,0)),1):controls.SetValue(i,gp_Pnt(*p))
        wire=BRepBuilderAPI_MakeWire();wire.Add(BRepBuilderAPI_MakeEdge(Geom_BezierCurve(controls)).Edge())
        for a,b in (((10,1,0),(10,0,0)),((10,0,0),(0,0,0)),((0,0,0),(0,1,0))):
            wire.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*a),gp_Pnt(*b)).Edge())
        solid=BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(wire.Wire()).Face(),gp_Vec(0,0,5)).Shape()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'extrusion.step';writer=STEPControl_Writer();previous=Interface_Static.IVal_s('write.surfacecurve.mode')
            try:
                Interface_Static.SetIVal_s('write.surfacecurve.mode',0);writer.Transfer(solid,STEPControl_AsIs);writer.Write(str(path))
            finally:Interface_Static.SetIVal_s('write.surfacecurve.mode',previous)
            with CadDocument.from_step(path,workers=1) as document:body=int(document.index.ids[document.model.bodies[0][0]])
            with NativeComponent(path,body) as component:
                p,t,f,proof=vector_component_mesh(component,.1)
                self.assertTrue(proof['closed_oriented_manifold'])
                self.assertEqual(proof['faces'],6)
                self.assertLess(abs(proof['volume_mm3']-250/3),1.)
                from build_vector_component import validate_supports
                self.assertLess(validate_supports(component,p,t,f,.1)['max_sampled_native_surface_distance_mm'],.1)

    def test_ear_clipping_keeps_collinear_boundary_vertices(self):
        polygon=np.array([[0,0,0],[1,0,0],[2,0,0],[2,2,0],[1,1,0],[0,2,0]],dtype=float)
        triangles=triangulate_polygon(polygon)
        self.assertEqual(len(triangles),4)
        self.assertEqual(set(triangles.ravel()),set(range(6)))
        with self.assertRaises(ValueError):orient_closed_mesh(polygon,triangles)


if __name__=='__main__':unittest.main()
