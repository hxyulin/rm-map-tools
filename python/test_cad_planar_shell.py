# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Planar skin invariants for apertures, materials and source boundaries."""
import unittest
import numpy as np
from cad_planar_shell import planar_skin


def grid(n=6,hole=False):
    p=np.array([[x,y,0] for y in range(n+1) for x in range(n+1)],float);t=[]
    for y in range(n):
        for x in range(n):
            if hole and 2<=x<4 and 2<=y<4:continue
            a=y*(n+1)+x;b=a+1;c=a+n+1;d=c+1;t.extend([(a,b,d),(a,d,c)])
    return p,np.asarray(t,dtype=np.int64)


class PlanarShellTests(unittest.TestCase):
    def test_grid_becomes_rectangle(self):
        p,t=grid();q,f,m,proof=planar_skin(p,t,np.zeros(len(t),int));self.assertEqual(len(f),2);self.assertEqual(len(q),4);self.assertEqual(proof['patches'][0]['sampled_deviation_mm']['max'],0);self.assertEqual(len(proof['boundary_vertex_positions_mm']),4);self.assertEqual(sorted(proof['patches'][0]['boundary_loops_vertex_indices'][0]),list(range(4)))

    def test_aperture_retains_inner_loop(self):
        p,t=grid(hole=True);q,f,m,proof=planar_skin(p,t,np.zeros(len(t),int));self.assertEqual(len(f),8);self.assertEqual(len(proof['patches'][0]['boundary_loops_source_vertices']),2)
        v=q[f];area=np.linalg.norm(np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]),axis=1).sum()/2;self.assertAlmostEqual(area,32)
        centroids=v.mean(1);self.assertFalse(np.any((centroids[:,0]>2)&(centroids[:,0]<4)&(centroids[:,1]>2)&(centroids[:,1]<4)))

    def test_material_boundary_and_protection(self):
        p,t=grid();m=(p[t].mean(1)[:,0]>3).astype(int);q,f,mm,proof=planar_skin(p,t,m,protected_material_ids=[1]);self.assertEqual(int((mm==1).sum()),int((m==1).sum()));np.testing.assert_array_equal(q[f[mm==1]],p[t[m==1]]);self.assertLess(int((mm==0).sum()),int((m==0).sum()));self.assertTrue(all(len(set(m[patch['input_triangle_indices']]))==1 for patch in proof['patches']))

    def test_curved_patch_cannot_accumulate_plane_drift(self):
        p,t=grid();p[:,2]=.03*p[:,0]**2;q,f,m,proof=planar_skin(p,t,np.zeros(len(t),int));self.assertTrue(all(r.get('maximum_planarity_mm',0)<=.001 for r in proof['patches']));self.assertGreater(len(f),2)

    def test_invalid_inputs_rejected(self):
        p,t=grid()
        for kwargs in [{'plane_tolerance_mm':0},{'boundary_tolerance_mm':float('nan')},{'minimum_triangles':1}]:
            with self.assertRaises(ValueError):planar_skin(p,t,np.zeros(len(t),int),**kwargs)
        with self.assertRaises(ValueError):planar_skin(p,t.astype(float),np.zeros(len(t),int))

if __name__=='__main__':unittest.main()
