import unittest
import numpy as np
from audit_geometry_duplicates import GeometryFingerprints
from audit_mesh_duplicates import prepare, match
from audit_body_symmetry import FrameFingerprints, estimate_removable_geometry
from types import SimpleNamespace


class FakeIndex:
    def __init__(self, records): self.records=records
    def text(self,row): return self.records[row]
    def r(self,number): return number if number in self.records else -1
    def tname(self,row): return self.records[row].split(b'=',1)[1].split(b'(',1)[0].decode()
    def args(self,row):
        text=self.records[row]
        return text[text.index(b'(')+1:text.rindex(b')')]


class DuplicateTests(unittest.TestCase):
    def test_graph_ids_names_comments_and_strings(self):
        ix=FakeIndex({1:b"#1=CARTESIAN_POINT('a',(1.,2.,3.));",
                      2:b"#2=CARTESIAN_POINT('b',(1.,2.,3.));",
                      3:b"#3=VERTEX_POINT('first',#1);",
                      4:b"#4=VERTEX_POINT('second', /* #99 */ #2);",
                      5:b"#5=CARTESIAN_POINT('a',(1.,2.,4.));",
                      6:b"#6=TEST('', 'literal #1');",
                      7:b"#7=TEST('', 'literal #2');"})
        hashes=GeometryFingerprints(ix)
        self.assertEqual(hashes.signature(3),hashes.signature(4))
        self.assertNotEqual(hashes.signature(1),hashes.signature(5))
        self.assertNotEqual(hashes.signature(6),hashes.signature(7))

    def test_graph_rejects_cycles_and_unresolved_references(self):
        for record in [b'#1=TEST(#1);',b'#1=TEST(#2);']:
            with self.assertRaises(ValueError):
                GeometryFingerprints(FakeIndex({1:record})).signature(1)

    def test_rigid_frame_hashes_points_and_directions_but_preserves_uv_and_radius(self):
        angle=0.37
        rotation=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
        frame=np.eye(4); frame[:3,:3]=rotation; frame[:3,3]=[12,34,56]
        point=np.array([1.,2,3]); direction=np.array([0.,1,0])
        def record(row,kind,value):
            return f"#{row}={kind}('',({','.join(format(n,'.15g') for n in value)}));".encode()
        ix=FakeIndex({1:record(1,'CARTESIAN_POINT',point),
                      2:record(2,'CARTESIAN_POINT',rotation@point+frame[:3,3]),
                      3:record(3,'DIRECTION',direction),
                      4:record(4,'DIRECTION',rotation@direction),
                      5:record(5,'CARTESIAN_POINT',[1,2]),
                      6:b"#6=SPHERE('',#1,2.);",7:b"#7=SPHERE('',#2,3.);"})
        first=FrameFingerprints(ix,np.eye(4)); second=FrameFingerprints(ix,frame)
        self.assertEqual(first.signature(1),second.signature(2))
        self.assertEqual(first.signature(3),second.signature(4))
        self.assertEqual(first.signature(5),second.signature(5))
        self.assertNotEqual(first.signature(6),second.signature(7))

    def test_size_bound_keeps_geometry_referenced_by_retained_bodies(self):
        # Body #2 duplicates #1, but point #5 is still used by retained bodies.
        ix=SimpleNamespace(n=7,size=100,lens=np.array([10]*7),
            refs=np.array([4,5,6,5,5,7]),refstart=np.array([0,2,4,6,6,6,6,6]),
            row=np.array([-1,0,1,2,3,4,5,6]),
            r=lambda eid:eid-1,rows_of=lambda *types:np.array([0,1,2]))
        result=estimate_removable_geometry(ix,[{'bodies':[{'id':1},{'id':2}]}])
        self.assertEqual(result['candidate_geometry_records'],2)
        self.assertEqual(result['candidate_geometry_text_bytes'],20)

    def fixture(self):
        p=np.array([[0.,0,0],[1,0,0],[0,2,0],[0,0,3]])
        t=np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
        return p,t,['red','green','blue','red']

    def test_rotation_translation_vertex_and_triangle_order(self):
        p,t,c=self.fixture(); ref=prepare('a',p,t,c)
        rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        permutation=np.array([3,1,0,2]); inv=np.argsort(permutation)
        transformed=(p@rotation.T+[9,8,7])[permutation]
        candidate=prepare('b',transformed,inv[t[::-1]][:,[1,2,0]],c[::-1])
        result=match(ref,candidate,1e-8)
        self.assertIsNotNone(result); self.assertFalse(result['mirrored']); self.assertTrue(result['same_colours'])
        matrix=np.array(result['candidate_to_reference_matrix'])
        np.testing.assert_allclose(transformed@matrix[:3,:3].T+matrix[:3,3],p[permutation],atol=1e-8)

    def test_reflection_and_colour_difference(self):
        p,t,c=self.fixture(); ref=prepare('a',p,t,c)
        candidate=prepare('b',p*[-1,1,1]+[1,2,3],t[:,[0,2,1]],['yellow']*4)
        result=match(ref,candidate,1e-8)
        self.assertIsNotNone(result); self.assertTrue(result['mirrored']); self.assertFalse(result['same_colours'])

    def test_rejects_changed_shape_and_connectivity(self):
        p,t,c=self.fixture(); ref=prepare('a',p,t,c)
        changed=p.copy(); changed[1,0]+=0.01
        self.assertIsNone(match(ref,prepare('b',changed,t,c),1e-5))
        altered=t.copy(); altered[0]=[0,1,3]
        self.assertIsNone(match(ref,prepare('b',p,altered,c),1e-5))

if __name__=='__main__': unittest.main()
