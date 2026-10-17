# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Compact-detail selection must preserve optics, isolated parts and structures."""
import unittest
import numpy as np
from cad_component_detail import compact_detail_filter,connected_pieces
from test_cad_collision_proxy import cube


def fixture():
    p,t=cube();chunks=[(p,t)]
    for origin,scale in [([21.,10,10],.1),([100.,10,10],.1),([21.,20,10],.1),([21.,0,0],.6)]:chunks.append((p*scale+origin,t))
    pp=[];tt=[];offset=0
    for p,t in chunks:pp.append(p);tt.append(t+offset);offset+=len(p)
    return np.concatenate(pp),np.concatenate(tt),np.repeat([0,0,0,1,0],12)


class CompactDetailTests(unittest.TestCase):
    def test_nearby_detail_omitted_isolated_and_optical_retained(self):
        p,t,m=fixture();before=p.copy();ids,proof=compact_detail_filter(p,t,m,protected_material_ids=[1])
        np.testing.assert_array_equal(ids,np.r_[np.arange(12),np.arange(24,60)])
        np.testing.assert_array_equal(p,before);self.assertEqual(sum(r['removed']for r in proof['pieces']),1)

    def test_exact_threshold_and_protected_port_stay(self):
        p,t,m=fixture();ids,_=compact_detail_filter(p,t,m,maximum_extent_mm=4,protected_material_ids=[1])
        self.assertEqual(len(ids),len(t)) # Small component's largest extent is exactly 4.
        ids,_=compact_detail_filter(p,t,m,protected_material_ids=[1],protected_triangle_indices=[12])
        self.assertEqual(len(ids),len(t))

    def test_small_parts_without_backing_are_retained(self):
        p,t=cube();p*=.1;ids,_=compact_detail_filter(p,t,np.zeros(len(t),int));np.testing.assert_array_equal(ids,np.arange(len(t)))

    def test_connectivity_joins_material_seams_without_rounding_source(self):
        p,t=cube();p=p[t].reshape(-1,3);t=np.arange(len(p)).reshape(-1,3);labels=connected_pieces(p,t)
        self.assertEqual(len(np.unique(labels)),1)

    def test_explicit_same_rigid_backing_admits_a_separate_small_member(self):
        bp,bt=cube();p,t=cube();p=p*.1+[21.,10,10]
        ids,_=compact_detail_filter(p,t,np.zeros(len(t),int),rigid_backing_mesh=(bp,bt))
        self.assertEqual(len(ids),0)
        p+=100
        ids,_=compact_detail_filter(p,t,np.zeros(len(t),int),rigid_backing_mesh=(bp,bt))
        self.assertEqual(len(ids),len(t))

    def test_bad_policy_and_mesh_rejected(self):
        p,t=cube()
        with self.assertRaises(ValueError):compact_detail_filter(p,t,np.zeros(len(t),int),maximum_extent_mm=-1)
        with self.assertRaises(ValueError):connected_pieces(p,np.array([[0,1,99]]))


if __name__=='__main__':unittest.main()
