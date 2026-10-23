"""Selection contract checks independent of the map fixtures."""
import unittest
import numpy as np
from run import choose


def row(detail, protected=False):
    # Large retained panel, and a separate detail immediately above it (mm).
    panel=np.array([[[-20,-20,0],[20,-20,0],[20,20,0]],
                    [[-20,-20,0],[20,20,0],[-20,20,0]]],float)
    g=np.concatenate([panel,np.asarray(detail,float)])
    return {'g':g,'labels':np.array([0,0]+[1]*len(detail)),
            'meta':[(0,2,False),(1,len(detail),protected)]}


class Policy(unittest.TestCase):
    def test_exact_thresholds_and_retention(self):
        r=row([[[0,0,2],[7,0,2],[0,7,2]]])
        keep,parts,_=choose(r,np.empty((0,2,3)),8)
        self.assertEqual(keep.tolist(),[True,True,False])
        self.assertEqual(parts[1]['maximum_vertex_backing_distance_mm'],2)
        r=row([[[0,0,2],[8,0,2],[0,7,2]]])
        self.assertTrue(choose(r,np.empty((0,2,3)),8)[0].all())
        r=row([[[0,0,8],[7,0,8],[0,7,8]]])
        self.assertTrue(choose(r,np.empty((0,2,3)),8)[0].all())

    def test_protected_material_and_optical_neighborhood(self):
        detail=[[[0,0,2],[7,0,2],[0,7,2]]]
        self.assertTrue(choose(row(detail,True),np.empty((0,2,3)),8)[0].all())
        boxes=np.array([[[15,0,2],[16,7,3]]])
        self.assertTrue(choose(row(detail),boxes,8)[0].all())
        boxes=np.array([[[15.01,0,2],[16,7,3]]])
        self.assertFalse(choose(row(detail),boxes,8)[0][-1])

    def test_no_backing_no_deletion(self):
        r={'g':np.array([[[0,0,0],[1,0,0],[0,1,0]]],float),'labels':np.array([0]),'meta':[(0,1,False)]}
        self.assertTrue(choose(r,np.empty((0,2,3)),17)[0].all())


if __name__=='__main__':unittest.main()
