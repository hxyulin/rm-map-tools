# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Light primitive shape, fit, winding and rear-clip invariants."""
import unittest
import numpy as np
from cad_light_primitives import rectangle_cover,fit_sphere,icosphere,clip_halfspace


class LightPrimitiveTests(unittest.TestCase):
    def test_icosphere_vertices_counts_and_outward_winding(self):
        for level in range(3):
            p,t=icosphere(level);np.testing.assert_allclose(np.linalg.norm(p,axis=1),1,atol=1e-14);self.assertEqual(len(t),20*4**level)
            tri=p[t];self.assertTrue(np.all(np.sum(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])*tri.mean(1),axis=1)>0))

    def test_sphere_fit_rebased_partial_cap(self):
        p,_=icosphere(2);p=p[p[:,2]>.5]*40+[1,1000,50];center,r,proof=fit_sphere(p);np.testing.assert_allclose(center,[1,1000,50],atol=1e-9);self.assertAlmostEqual(r,40,places=9)
        p[0,0]+=1
        with self.assertRaises(ValueError):fit_sphere(p)

    def test_clip_keeps_chords_behind_sphere_and_rejects_rear(self):
        p,t=icosphere(1);p,t=clip_halfspace(p,t,[0,0,1],.6);self.assertTrue(np.all(p[:,2]>=.6-1e-12));self.assertTrue(np.all(np.linalg.norm(p,axis=1)<=1+1e-12));self.assertLess(len(t),80);self.assertGreater(len(t),0)

    def test_quad_covers_rotated_planar_trim_and_insets(self):
        x=np.array([1,1,0])/np.sqrt(2);y=np.array([0,0,1]);n=np.cross(x,y);source=np.array([[-2,-1],[2,-1],[2,1],[-2,1]])@np.array([x,y])+[0,20,50];q,t,proof=rectangle_cover(source,n,inset_mm=.1);self.assertEqual(len(t),2);np.testing.assert_allclose((q-source.mean(0))@n,-.1,atol=1e-12);self.assertAlmostEqual(proof['rectangle_area_mm2'],8,places=9)

    def test_invalid_primitive_policies_reject(self):
        with self.assertRaises(ValueError):icosphere(True)
        with self.assertRaises(ValueError):rectangle_cover([[0,0,0],[1,0,0],[0,1,1]],[0,0,1])


if __name__=='__main__':unittest.main()
