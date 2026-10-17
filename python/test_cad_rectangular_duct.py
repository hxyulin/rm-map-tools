# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check proxy topology, material volume and its uninterrupted opening."""
import unittest
import numpy as np
from cad_rectangular_duct import flanged_duct


class RectangularDuctTests(unittest.TestCase):
    def test_closed_material_and_open_passage(self):
        p,t,parts=flanged_duct(duct_length_mm=300,duct_width_mm=160,duct_height_mm=280,wall_mm=3,flange_width_mm=210,flange_height_mm=330,flange_thickness_mm=12)
        self.assertEqual(len(t),56);self.assertEqual(np.bincount(parts).tolist(),[32,24])
        edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);_,counts=np.unique(edges,axis=0,return_counts=True);self.assertTrue(np.all(counts==2))
        g=p[t];volume=np.einsum('ij,ij->i',g[:,0],np.cross(g[:,1],g[:,2])).sum()/6
        expected=300*(160*280-154*274)+12*(210*330-154*274);self.assertAlmostEqual(volume,expected)
        # No cap triangle bridges the interior rectangle at either end.
        for x in [0,312]:
            faces=g[np.all(g[:,:,0]==x,axis=1)];centres=faces.mean(1);self.assertTrue(np.all((abs(centres[:,1])>=77)|(abs(centres[:,2])>=137)))
        self.assertTrue(np.all(np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1)>0))

    def test_invalid_dimensions(self):
        args=dict(duct_length_mm=300,duct_width_mm=160,duct_height_mm=280,wall_mm=3,flange_width_mm=210,flange_height_mm=330,flange_thickness_mm=12)
        for key,value in [('wall_mm',80),('flange_width_mm',160),('duct_length_mm',float('nan')),('wall_mm',True),('flange_thickness_mm',-1)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):flanged_duct(**{**args,key:value})
