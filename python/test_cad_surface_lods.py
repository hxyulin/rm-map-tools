# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Protection and native aperture invariants for separate Base LOD outputs."""
import unittest
import numpy as np
from cad_surface_lods import material_lod,profile_prism
from cad_wall_fill import shape_map,volume
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.TopAbs import TopAbs_FACE,TopAbs_REVERSED
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir


class SurfaceLodTests(unittest.TestCase):
    def test_light_strip_and_material_boundary_retained(self):
        p=np.array([[x,y,0.] for y in range(9) for x in range(9)])+np.array([1000.,2000.,3000.]);t=[];m=[]
        for y in range(8):
            for x in range(8):
                k=y*9+x;t.extend([(k,k+1,k+10),(k,k+10,k+9)]);m.extend([int(x==4)]*2)
        t=np.array(t);m=np.array(m);out,f,mat,proof=material_lod(p,t,m,error_mm=.1,protected_material_ids=(1,))
        np.testing.assert_array_equal(out[f[mat==1]],p[t[m==1]])
        # Border includes every point along both sides of the protected strip.
        for x in (4,5):
            expected=p[(p[:,0]==1000+x)];actual=out[np.unique(f[mat==0])]
            self.assertTrue(all(np.any(np.all(actual==point,axis=1)) for point in expected))
        self.assertLess(len(f),len(t));self.assertTrue(proof['locked_material_borders'])

    def test_profile_keeps_large_hole_fills_small_hole_and_signed_depth(self):
        box=BRepPrimAPI_MakeBox(30,20,2).Shape()
        for x,r in ((5,1),(20,3)):
            tool=BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,10,-1),gp_Dir(0,0,1)),r,4).Shape();box=BRepAlgoAPI_Cut(box,tool).Shape()
        faces=shape_map(box,TopAbs_FACE);face=None
        for i in range(1,faces.Extent()+1):
            candidate=faces.FindKey(i);s=BRepAdaptor_Surface(__import__('OCP.TopoDS',fromlist=['TopoDS']).TopoDS.Face(candidate))
            if s.GetType()==GeomAbs_Plane and abs(s.Plane().Location().Z()-2)<1e-6:face=candidate;break
        result,proof=profile_prism(face,depth_mm=-2,maximum_filled_hole_area_mm2=4)
        self.assertEqual(len(proof['filled_hole_areas_mm2']),1);self.assertEqual(len(proof['retained_hole_areas_mm2']),1)
        self.assertAlmostEqual(abs(volume(result)),(600-9*np.pi)*2,places=5)
        self.assertTrue(proof['outer_wire_unchanged'])
        reversed_result,reversed_proof=profile_prism(face.Oriented(TopAbs_REVERSED),depth_mm=-2,maximum_filled_hole_area_mm2=4)
        self.assertAlmostEqual(abs(volume(reversed_result)),abs(volume(result)),places=5)
        self.assertEqual(reversed_proof['retained_hole_areas_mm2'],proof['retained_hole_areas_mm2'])

    def test_sampled_failure_refines_metric_instead_of_relaxing_limit(self):
        from unittest.mock import patch
        p=np.array([[0.,0,0],[1,0,0],[0,1,0]])
        with patch('mesh_quality.deviation',side_effect=[{'max':2.,'p99':2.,'sample_count':1},{'max':.1,'p99':.1,'sample_count':1}]), patch('simplify_package.simplify_mesh',return_value=(p,np.array([[0,1,2]]),.01)) as simplify:
            _,_,_,proof=material_lod(p,[[0,1,2]],[0],error_mm=.25,sampled_limit_mm=.5)
        self.assertEqual([call.args[2] for call in simplify.call_args_list],[.25,.125])
        self.assertEqual(proof['regions'][0]['sampled_limit_mm'],.5)

    def test_led_override_has_tighter_error_and_sampled_budget(self):
        from unittest.mock import patch
        p=np.array([[0.,0,0],[1,0,0],[0,1,0],[2,0,0],[3,0,0],[2,1,0]])
        def fake(points,faces,error,**kwargs):return points,faces,0.
        with patch('simplify_package.simplify_mesh',side_effect=fake) as simplify:
            _,_,_,proof=material_lod(p,[[0,1,2],[3,4,5]],[0,1],error_mm=.25,sampled_limit_mm=1.,material_policies={1:{'error_mm':.025,'sampled_limit_mm':.1}})
        self.assertEqual([call.args[2] for call in simplify.call_args_list],[.25,.025])
        self.assertEqual([r['sampled_limit_mm'] for r in proof['regions']],[1.,.1])

    def test_invalid_policies_reject(self):
        with self.assertRaises(ValueError):material_lod([[0,0,0]],[[0,0,0]],[0],error_mm=-1)
        with self.assertRaises(ValueError):profile_prism(None,depth_mm=0)


if __name__=='__main__':unittest.main()
