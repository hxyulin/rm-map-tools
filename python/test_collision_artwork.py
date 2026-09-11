import tempfile
from pathlib import Path
import unittest
import numpy as np
from export_field_package import GlbWriter
from gltf_scene import read_glb,mesh_instances
from collision_artwork import strip

class CollisionArtworkTests(unittest.TestCase):
    def fixture(self,root):
        w=GlbWriter('root',{'version':'2.0'})
        p=np.array([[0.,0,0],[1,0,0],[0,1,0]])
        w.add_node('paint',p,np.array([[0,1,2]]),['1,1,1'])
        w.add_node('backing',p+[0,0,-.01],np.array([[0,1,2]]),['0,0,0'])
        w.write(root/'collision.glb')
        return read_glb(root/'collision.glb')

    def test_removes_only_selected_occurrence_of_a_shared_mesh(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc,binary=self.fixture(Path(tmp))
            doc['nodes'].append({'name':'other_paint','mesh':doc['nodes'][1]['mesh'],'translation':[2,0,0]})
            doc['nodes'][0]['children'].append(3)
            before=list(mesh_instances(doc,binary))
            out,packed,report=strip(doc,binary,[dict(node='paint',material='colour_1,1,1')])
            after=list(mesh_instances(out,packed))
            self.assertEqual(len(after),2)
            self.assertEqual(report[0]['triangles'],1)
            self.assertNotIn('mesh',out['nodes'][1])
            self.assertIn('mesh',doc['nodes'][1])
            for old,new in zip(before[1:],after):
                np.testing.assert_array_equal(old[2],new[2])
                np.testing.assert_array_equal(old[3],new[3])

    def test_solid_geometry_is_not_removed_as_artwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            w=GlbWriter('root',{'version':'2.0'})
            p=np.array([[0.,0,0],[1,0,0],[0,1,0],[0,0,1]])
            w.add_node('solid',p,np.array([[0,1,2],[0,1,3]]),['1,1,1']*2)
            w.write(root/'solid.glb')
            doc,binary=read_glb(root/'solid.glb')
            with self.assertRaisesRegex(ValueError,'not planar'):
                strip(doc,binary,[dict(node='solid',material='colour_1,1,1')])

    def test_missing_ambiguous_and_duplicate_selectors_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc,binary=self.fixture(Path(tmp))
            sel=dict(node='paint',material='colour_1,1,1')
            with self.assertRaises(ValueError):strip(doc,binary,[dict(sel,node='missing')])
            with self.assertRaises(ValueError):strip(doc,binary,[sel,sel])
            doc['nodes'].append({'name':'paint','mesh':0});doc['nodes'][0]['children'].append(3)
            with self.assertRaises(ValueError):strip(doc,binary,[sel])

if __name__=='__main__':unittest.main()
