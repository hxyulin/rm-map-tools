# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'python'),str(Path(__file__).parent)]
from curve import *
def shell(radii,segments=24):
 angles=np.arange(segments)*2*np.pi/segments;p=np.array([[[r*np.cos(t),i*10,r*np.sin(t)] for t in angles] for i,r in enumerate(radii)]).reshape(-1,3);f=[]
 for i in range(len(radii)-1):
  for j in range(segments):
   a=i*segments+j;b=i*segments+(j+1)%segments;f.extend([[a,b,b+segments],[a,b+segments,a+segments]])
 return p[np.array(f)]
class Curves(unittest.TestCase):
 def test_cylinder_boundary(self):
  g=shell([50,50,50]);q,m=retriangulate(g,axis=[0,1,0],anchor=[0,0,0],radius=50,sectors=8)
  self.assertLessEqual(boundary_error(g,q)['maximum_sampled_boundary_mm'],.001)
  self.assertLessEqual(measure(g,q,1)['max_mm'],1.8)
 def test_open_socket(self):
  g=shell([50,50,50]);g=g[12:];q,m=retriangulate(g,axis=[0,1,0],anchor=[0,0,0],radius=50,sectors=8)
  self.assertLessEqual(boundary_error(g,q)['maximum_sampled_boundary_mm'],.001)
 def test_hidden_nested_sheet_is_rejected(self):
  g=np.concatenate([shell([50,50,50]),shell([45,45,45])]);q,m=retriangulate(g,axis=[0,1,0],anchor=[0,0,0],radius=50,sectors=8)
  self.assertGreater(boundary_error(g,q)['maximum_sampled_boundary_mm'],1)
 def test_source_samples_capture_rounding_loss(self):
  g=shell([50,65,50]);q,m=retriangulate(g,axis=[0,1,0],anchor=[0,0,0],radius=50,sectors=8)
  self.assertGreater(measure(g,q,1)['max_mm'],10)
if __name__=='__main__':unittest.main()
