# SPDX-License-Identifier: MIT OR Apache-2.0
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gltf_scene import read_glb_nodes, scene_nodes, write_glb


def fixture():
    points = np.array([[1, 0, 0], [2, 0, 0], [1, 1, 0]], dtype='<f4')
    binary = points.tobytes()
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'name': 'root', 'translation': [10, 0, 0], 'children': [1, 2]},
                     {'name': 'plate', 'mesh': 0, 'translation': [0, 2, 0]},
                     {'name': 'text', 'mesh': 0, 'translation': [0, 0, 1]}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'material': 0}]}],
           'materials': [{'name': 'paint', 'pbrMetallicRoughness': {'baseColorFactor': [1, 0, 0, 1]}}],
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3'}],
           'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary)}],
           'buffers': [{'byteLength': len(binary)}]}
    return doc, binary


class GltfSceneTests(unittest.TestCase):
    def test_nested_transform_shared_mesh_and_scene_selection(self):
        doc, binary = fixture()
        doc['nodes'][0]['rotation'] = [0, 0, np.sqrt(.5), np.sqrt(.5)]
        doc['nodes'].append({'mesh': 0, 'translation': [999, 999, 999]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'a.glb'
            write_glb(path, doc, binary)
            records = list(read_glb_nodes(path))
        self.assertEqual(len(records), 2)
        np.testing.assert_allclose(records[0][1], [[8, 1, 0], [8, 2, 0], [7, 1, 0]], atol=1e-12)
        np.testing.assert_allclose(records[1][1], [[10, 1, 1], [10, 2, 1], [9, 1, 1]], atol=1e-12)

    def test_reflection_reverses_winding(self):
        doc, binary = fixture()
        doc['nodes'][0]['scale'] = [-1, 1, 1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'a.glb'
            write_glb(path, doc, binary)
            records = list(read_glb_nodes(path))
        np.testing.assert_array_equal(records[0][2], [[0, 2, 1]])

    def test_rejects_cycles_and_multiple_parents(self):
        doc, _ = fixture()
        doc['nodes'][1]['children'] = [2]
        with self.assertRaises(ValueError):
            list(scene_nodes(doc))


if __name__ == '__main__':
    unittest.main()
