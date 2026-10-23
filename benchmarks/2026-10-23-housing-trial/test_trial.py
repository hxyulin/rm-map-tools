# SPDX-License-Identifier: MIT OR Apache-2.0
import unittest
import numpy as np
from trial import profile
from cad_collision_profiles import prism_mesh,mesh_metrics
from apertures import fill

class ProfileTests(unittest.TestCase):
 def sheet(self,hole_width):
  h=hole_width/2
  loops=[{'outer':True,'points_mm':np.array([[-100,-100,0],[100,-100,0],[100,100,0],[-100,100,0]])},{'outer':False,'points_mm':np.array([[-h,-h,0],[h,-h,0],[h,h,0],[-h,h,0]])}]
  p,t,_=prism_mesh(loops,np.array([0.,0.,1.]),3)
  return p[t]
 def test_major_hole_survives(self):
  q,t,row=profile(self.sheet(20),np.array([0.,0.,1.]),hole=17)
  self.assertEqual(row['retained_holes'],1);self.assertEqual(row['closed_holes'],[]);self.assertTrue(row['topology']['closed_oriented_manifold'])
 def test_small_hole_explicitly_removed(self):
  q,t,row=profile(self.sheet(5),np.array([0.,0.,1.]),hole=17)
  self.assertEqual(row['retained_holes'],0);self.assertEqual(len(row['closed_holes']),1);self.assertEqual(len(t),12)
 def test_finite_aperture_fill_closed(self):
  g=self.sheet(5);out,rows=fill(g,g)
  self.assertTrue(rows);self.assertLess(len(out),len(g));q,inv=np.unique(out.reshape(-1,3),axis=0,return_inverse=True)
  self.assertTrue(mesh_metrics(q,inv.reshape(-1,3))['closed_oriented_manifold'])
 def test_optical_intersection_guard(self):
  from verify import contacts
  a=np.array([[[0.,0.,0.],[10.,0.,0.],[0.,10.,0.]]]);b=np.array([[[2.,1.,-1.],[2.,1.,1.],[2.,5.,0.]]])
  self.assertGreater(contacts(a,b),0);self.assertEqual(contacts(a,b+100),0)
 def test_broad_opening_untouched(self):
  g=self.sheet(20);out,rows=fill(g,g)
  self.assertEqual(rows,[]);np.testing.assert_array_equal(out,g)
if __name__=='__main__':unittest.main()
