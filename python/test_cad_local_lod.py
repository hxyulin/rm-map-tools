# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Local refinement, seam locks and source-membership invariants."""
import unittest
from unittest.mock import patch
import numpy as np
from cad_local_lod import adaptive_material_lod,guarded_vertex_lod


def grid(size=10):
    p=np.array([[x,y,0.] for y in range(size+1) for x in range(size+1)]);t=[]
    for y in range(size):
        for x in range(size):
            k=y*(size+1)+x;t.extend([(k,k+1,k+size+2),(k,k+size+2,k+size+1)])
    return p,np.array(t)


class LocalLodTests(unittest.TestCase):
    def test_shared_frame_locks_material_seam_and_keeps_small_component(self):
        p,t=grid();p+=np.array([1250.1,2300.3,-70.2]);m=np.array([int(p[face].mean(0)[0]>1255.1) for face in t]);out,faces,materials,proof=adaptive_material_lod(p,t,m,error_mm=.25,sampled_limit_mm=1,sample_count=96)
        self.assertLess(len(faces),len(t));self.assertTrue(proof['locked_patch_borders']);self.assertLess(proof['maximum_input_quantization_mm'],.001)
        for material in (0,1):
            actual=out[np.unique(faces[materials==material])];seam=p[np.isclose(p[:,0],1255.1)]
            for point in seam:self.assertLess(np.linalg.norm(actual-point,axis=1).min(),.001)
        q=p+np.array([0,0,3]);out,faces,_,_=adaptive_material_lod(np.concatenate([p,q]),np.concatenate([t,t+len(p)]),np.zeros(2*len(t),int),sample_count=96)
        self.assertTrue(np.any(out[faces][:,:,2]<-69));self.assertTrue(np.any(out[faces][:,:,2]>-69))

    def test_failed_parent_splits_only_failed_region_and_keeps_guard(self):
        p,t=grid(8);calls=[]
        def simplify(points,faces,error,**kwargs):calls.append(error);return points,faces,error
        measurements=[{'max':2.,'p99':2.,'sample_count':1}]+[{'max':.1,'p99':.1,'sample_count':1}]*2
        with patch('simplify_package.simplify_mesh',side_effect=simplify),patch('mesh_quality.deviation',side_effect=measurements):
            _,faces,_,proof=adaptive_material_lod(p,t,np.zeros(len(t),int),sample_count=96,maximum_depth=1,minimum_patch_triangles=16)
        self.assertEqual(len(proof['splits']),1);self.assertEqual(len(proof['leaves']),2);self.assertEqual(proof['sampled_limit_mm'],1);self.assertEqual(calls,[.25,.25,.25])
        membership=sum([leaf['input_triangle_indices'] for leaf in proof['leaves']],[]);self.assertEqual(sorted(membership),list(range(len(t))))

    def test_leaf_refines_metric_and_unresolved_leaf_keeps_input(self):
        p,t=grid(4)
        def simplify(points,faces,error,**kwargs):return points,faces,error
        with patch('simplify_package.simplify_mesh',side_effect=simplify),patch('mesh_quality.deviation',return_value={'max':2.,'p99':2.,'sample_count':1}):
            out,faces,_,proof=adaptive_material_lod(p,t,np.zeros(len(t),int),sample_count=96,maximum_depth=0)
        self.assertEqual(proof['leaves'][0]['operation'],'retain-quantized-input');self.assertEqual(len(faces),len(t));self.assertEqual([x['requested_error_mm'] for x in proof['leaves'][0]['trials']],[.25,.125,.0625,.03125,.015625]);np.testing.assert_allclose(out[faces],p[t],atol=.001)

    def test_missing_locked_border_rejects_trial(self):
        p,t=grid(4)
        with patch('simplify_package.simplify_mesh',return_value=(p[:3],np.array([[0,1,2]]),.1)):
            _,faces,_,proof=adaptive_material_lod(p,t,np.zeros(len(t),int),sample_count=96,maximum_depth=0)
        self.assertEqual(len(faces),len(t));self.assertEqual(proof['leaves'][0]['operation'],'retain-quantized-input')

    def test_invalid_policies_and_imprecise_frame_reject(self):
        p,t=grid(4);m=np.zeros(len(t),int)
        for kwargs in ({'error_mm':-1},{'maximum_depth':-1},{'minimum_patch_triangles':1},{'sample_count':1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):adaptive_material_lod(p,t,m,**kwargs)
        p[0,0]=1e10+.17
        with self.assertRaises(ValueError):adaptive_material_lod(p,t,m)


class VertexGuardTests(unittest.TestCase):
    def test_explicit_vertex_locks_preserve_interior_and_weld_aliases(self):
        from simplify_package import simplify_mesh
        p,t=grid();center=5*11+5;p=np.concatenate([p,p[[center]]]);t[t==center]=len(p)-1
        q,u,_=simplify_mesh(p,t,.25,locked_vertex_indices=[center])
        self.assertTrue(np.any(np.all(q[np.unique(u)]==p[center],axis=1)))
        q,u,_=simplify_mesh(p,t,.25,locked_vertex_indices=np.arange(len(p)))
        self.assertEqual(len(u),len(t))
        for locks in ([-1],[len(p)],[.5],[[1]]):
            with self.subTest(locks=locks):
                with self.assertRaises(ValueError):simplify_mesh(p,t,.25,locked_vertex_indices=locks)

    def test_guard_repairs_only_failing_neighborhood_at_same_metric(self):
        p,t=grid();m=np.zeros(len(t),int);counter=[0]
        def measured(samples,points,faces):
            values=np.zeros(len(samples));counter[0]+=1
            if counter[0]==1:values[0]=2
            return values
        with patch('mesh_quality.distances',side_effect=measured):
            q,u,_,proof=guarded_vertex_lod(p,t,m,sample_count=96)
        trials=proof['regions'][0]['trials'];self.assertEqual(len(trials),2);self.assertEqual(trials[0]['locked_vertices'],0);self.assertEqual(trials[1]['locked_vertices'],3);self.assertEqual(proof['error_mm'],.25);self.assertEqual(proof['sampled_limit_mm'],1)
        self.assertLess(len(u),len(t));self.assertEqual(proof['regions'][0]['operation'],'guarded-vertex-lod')

    def test_unresolved_guard_restores_original_region(self):
        p,t=grid(4);m=np.zeros(len(t),int)
        with patch('mesh_quality.distances',side_effect=lambda samples,points,faces:np.full(len(samples),2.)):
            q,u,_,proof=guarded_vertex_lod(p,t,m,sample_count=96,maximum_iterations=2)
        self.assertEqual(proof['regions'][0]['operation'],'retain-input');np.testing.assert_array_equal(q[u],p[t])

    def test_material_seams_and_disconnected_geometry_survive(self):
        p,t=grid();p=np.concatenate([p,p+[0,0,2]]);t=np.concatenate([t,t+121]);m=np.repeat([0,1],200)
        q,u,materials,proof=guarded_vertex_lod(p,t,m,sample_count=96)
        self.assertEqual(set(materials),{0,1});self.assertEqual(len(proof['regions']),2)
        self.assertTrue(np.all(q[u[materials==0]][:,:,2]==0));self.assertTrue(np.all(q[u[materials==1]][:,:,2]==2))

class NativeOutlineProtectionTests(unittest.TestCase):
    def test_native_collinear_subdivisions_do_not_require_extra_locks(self):
        from cad_local_lod import planar_outline_vertices
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace
        from OCP.gp import gp_Pnt
        polygon=BRepBuilderAPI_MakePolygon()
        for point in [(0,0,0),(1,0,0),(2,0,0),(4,0,0),(4,2,0),(0,2,0)]:polygon.Add(gp_Pnt(*point))
        polygon.Close();face=BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
        dense,_=planar_outline_vertices(face,minimum_face_area_mm2=1)
        sparse,proof=planar_outline_vertices(face,minimum_face_area_mm2=1,corner_turn_rad=np.deg2rad(15))
        self.assertEqual(len(dense),6);self.assertEqual(len(sparse),4);self.assertEqual(proof['wires'][0]['native_vertices'],6)
        self.assertEqual(set(map(tuple,sparse)),{(0.,0.,0.),(4.,0.,0.),(4.,2.,0.),(0.,2.,0.)})

    def test_native_selection_keeps_large_aperture_and_excludes_small_one(self):
        from cad_local_lod import planar_outline_vertices
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir
        shape=BRepPrimAPI_MakeBox(100,100,4).Shape()
        for x,radius in [(25,6),(70,10)]:shape=BRepAlgoAPI_Cut(shape,BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,50,-1),gp_Dir(0,0,1)),radius,6).Shape()).Shape()
        _,proof=planar_outline_vertices(shape)
        inner=[w for w in proof['wires'] if not w['outer_wire']]
        self.assertEqual(len(inner),2)
        for wire in inner:self.assertAlmostEqual(wire['width_upper_bound_mm'],20,places=5)

    def test_seed_locks_are_present_from_the_first_trial(self):
        p,t=grid();q,u,_,proof=guarded_vertex_lod(p,t,np.zeros(len(t),int),sample_count=96,protected_vertex_indices=[60])
        self.assertEqual(proof['regions'][0]['initial_protected_vertices'],1);self.assertEqual(proof['regions'][0]['trials'][0]['locked_vertices'],1);self.assertTrue(np.any(np.all(q[np.unique(u)]==p[60],axis=1)))
        for seed in ([-1],[len(p)],[1.5]):
            with self.assertRaises(ValueError):guarded_vertex_lod(p,t,np.zeros(len(t),int),protected_vertex_indices=seed)

if __name__=='__main__':unittest.main()
