# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Dense LOD preserves openings, material ownership and exact optical patches."""
import unittest
from unittest.mock import patch
import numpy as np
from cad_dense_lod import dense_lod
from mesh_quality import distances
from test_cad_collision_proxy import cube, subdivide


class DenseLodTests(unittest.TestCase):
    def test_subdivided_box_reduces_without_moving_surface(self):
        p,t=subdivide(*cube()); original=p.copy(); q,f,k,proof=dense_lod(p,t,np.zeros(len(t),int),maximum_distance_mm=.1)
        self.assertLess(len(f),len(t));self.assertFalse(proof['retained_input'])
        self.assertLess(distances(p,q,f).max(),.001);np.testing.assert_array_equal(p,original)

    def test_open_face_stays_open(self):
        p,t=cube();p,t=subdivide(p,t[2:]);q,f,k,proof=dense_lod(p,t,np.zeros(len(t),int))
        self.assertGreater(distances(np.array([[0.,15,20]]),q,f)[0],9.99)

    def test_optical_patch_is_exact_despite_float32_backend(self):
        p,t=subdivide(*cube());p += [.123456789,1000.123456789,-42.1357913579]
        m=(p[t].mean(1)[:,0] < .124).astype(int)
        q,f,k,proof=dense_lod(p,t,m,protected_material_ids=[1])
        self.assertLess(len(f),len(t))
        self.assertEqual(sorted(map(tuple,p[t[m==1]].reshape(-1,9))),sorted(map(tuple,q[f[k==1]].reshape(-1,9))))

    def test_nearby_other_material_cannot_hide_bad_replacement(self):
        # Global distance would be zero after swapping the two paint surfaces.
        p=np.array([[0.,0,0],[10,0,0],[0,10,0],[0,0,5],[10,0,5],[0,10,5]])
        t=np.array([[0,1,2],[3,4,5]]);m=np.array([0,1])
        with patch('cad_dense_lod.guarded_vertex_lod',return_value=(p,t[::-1],m,{})):
            q,f,k,proof=dense_lod(p,t,m,maximum_distance_mm=1)
        np.testing.assert_array_equal(f,t);self.assertTrue(proof['retained_input'])
        self.assertFalse(proof['trials'][0]['accepted'])
        self.assertEqual(proof['trials'][0]['maximum_sampled_distance_mm'],5)

    def test_policy_rejected(self):
        p,t=cube()
        with self.assertRaises(ValueError):dense_lod(p,t,np.zeros(len(t),int),maximum_distance_mm=float('nan'))


if __name__=='__main__':unittest.main()
