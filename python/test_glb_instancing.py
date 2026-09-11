"""Regression checks for compact, shared export geometry."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from export_field_package import GlbWriter
from gltf_scene import read_glb, read_glb_nodes, read_glb_local_nodes, accessor


class InstancingTests(unittest.TestCase):
    def test_shared_geometry_transforms_colours_and_edges(self):
        p = np.array([[0.,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1]])
        t = np.array([[0,1,2],[0,2,3],[0,4,1]])
        w = GlbWriter('root', {'version':'2.0'})
        w.add_node('first', p, t, [None]*3)
        m = np.eye(4); m[:3,:3] = [[0,-1,0],[1,0,0],[0,0,1]]; m[:3,3] = [2,3,4]
        w.add_node('second', p, t, [None]*3, matrix=m)
        mirror = np.diag([-1.,1,1,1])
        w.add_node('mirror', p, t, [None]*3, matrix=mirror)
        w.add_node('painted', p, t, ['1,0,0']*3)
        self.assertEqual(len(w.meshes), 2)
        self.assertEqual(w.triangles, 12)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'test.glb'; w.write(path)
            doc, binary = read_glb(path)
            nodes = list(read_glb_nodes(path))
            local = list(read_glb_local_nodes(path))
            rebuilt = GlbWriter('root', {'version':'2.0'})
            for name, points, tris, colours, world in local:
                rebuilt.add_node(name, points, tris, colours, matrix=world)
            self.assertEqual(len(rebuilt.meshes), 2)
            rebuilt.write(Path(d)/'rebuilt.glb')
            roundtrip = list(read_glb_nodes(Path(d)/'rebuilt.glb'))
            for original, result in zip(nodes, roundtrip):
                np.testing.assert_allclose(original[1][original[2]], result[1][result[2]])
        for (_, points, tris, _), transform in zip(nodes, [np.eye(4),m,mirror,np.eye(4)]):
            expected = p[t] @ transform[:3,:3].T + transform[:3,3]
            if np.linalg.det(transform[:3,:3]) < 0:
                expected = expected[:,[0,2,1]]
            np.testing.assert_allclose(points[tris], expected, atol=1e-7)
        prim = doc['meshes'][0]['primitives'][0]
        self.assertEqual(len(accessor(doc,binary,prim['attributes']['POSITION'])), 7)
        self.assertEqual(doc['accessors'][prim['indices']]['componentType'],5123)
        normals = accessor(doc,binary,prim['attributes']['NORMAL'])
        self.assertEqual(len(np.unique(normals,axis=0)),2)

    def test_large_mesh_uses_uint32_indices(self):
        p = np.zeros((65538, 3)); p[:, 0] = np.arange(len(p))
        t = np.arange(len(p)).reshape(-1, 3)
        writer = GlbWriter('root', {'version':'2.0'})
        writer.add_node('large', p, t, [None]*len(t))
        primitive = writer.meshes[0]['primitives'][0]
        self.assertEqual(writer.accessors[primitive['indices']]['componentType'], 5125)

    def test_empty_anchor_keeps_placement_and_invalid_matrix_is_rejected(self):
        writer = GlbWriter('root', {'version':'2.0'})
        matrix = np.eye(4); matrix[0,3] = 5
        writer.add_node('anchor', np.empty((0,3)), np.empty((0,3),int), [], matrix=matrix)
        self.assertEqual(writer.nodes[0]['matrix'][12], 5)
        with self.assertRaises(ValueError):
            writer.add_node('bad', [], [], [], matrix=np.zeros((3,3)))

if __name__ == '__main__':
    unittest.main()
