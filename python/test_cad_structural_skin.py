# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check selected structural LOD budgets without rounding protected artwork."""
import unittest
import numpy as np
from cad_structural_skin import structural_skin


class StructuralSkinTests(unittest.TestCase):
    def test_curved_detail_and_protected_face_keep_source_immutable(self):
        p=np.array([[x,y,.02*x*x] for y in range(9) for x in range(13)],float)
        t=[]
        for y in range(8):
            for x in range(12):
                a=y*13+x;t.extend([[a,a+1,a+14],[a,a+14,a+13]])
        t=np.array(t);m=(p[t].mean(1)[:,0]<3).astype(int)
        before=p.copy();q,f,k,proof=structural_skin(p,t,m,protected_material_ids=[1],outline_points_mm=p[[0,12,104,116]],nominal_error_mm=.25,sampled_limit_mm=.4,sample_count=2048)
        self.assertLessEqual(len(f),len(t));self.assertLessEqual(proof['sampled_deviation_mm']['max'],.401)
        self.assertEqual(sorted(map(tuple,p[t[m==1]].reshape(-1,9))),sorted(map(tuple,q[f[k==1]].reshape(-1,9))))
        np.testing.assert_array_equal(p,before)
        with self.assertRaises(ValueError):structural_skin(p,t,m,sampled_limit_mm=float('nan'))
