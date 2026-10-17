# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check rigid sharing without dropping artwork UVs, PNG bytes or material state."""
import copy
import tempfile
from pathlib import Path
import unittest
import numpy as np
from cad_glb_composition import RigidComposer
from export_field_package import GlbWriter
from gltf_scene import read_glb, mesh_instances, accessor


class GlbCompositionTests(unittest.TestCase):
    def test_repeated_textured_definition(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.glb'; writer = GlbWriter('source', {'version': '2.0'})
            writer.add_node('face', np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0]]), np.array([[0, 1, 2]]), ['1,0,0'])
            writer.write(path); d, b = read_glb(path); b = bytearray(b)
            offset = len(b); uv = np.array([[0, 0], [1, 0], [0, 1]], dtype='<f4'); b.extend(uv.tobytes())
            d['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': uv.nbytes})
            d['accessors'].append({'bufferView': len(d['bufferViews']) - 1, 'componentType': 5126, 'count': 3, 'type': 'VEC2'})
            d['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_0'] = len(d['accessors']) - 1
            image = b'source-png-payload'; offset = len(b); b.extend(image)
            d['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(image)})
            d['images'] = [{'bufferView': len(d['bufferViews']) - 1, 'mimeType': 'image/png'}]
            d['textures'] = [{'source': 0}]; d['materials'][0]['pbrMetallicRoughness']['baseColorTexture'] = {'index': 0}
            composed = RigidComposer(); composed.document['nodes'].append({'name': 'root'})
            composed.document['scenes'][0]['nodes'] = [0]
            for name in ['first', 'second']: composed.append_definition(name, d, bytes(b))
            for _ in range(2): composed.instantiate('second', 0)
            out = composed.document; instances = list(mesh_instances(out, composed.binary))
            self.assertEqual(len(instances), 2); self.assertEqual(len(out['meshes']), 2)
            actual_mesh_ids = {out['nodes'][i]['mesh'] for i, _, _, _, _ in instances}
            self.assertEqual(actual_mesh_ids, {1})
            prim = out['meshes'][1]['primitives'][0]
            np.testing.assert_array_equal(accessor(out, composed.binary, prim['attributes']['TEXCOORD_0']), uv)
            mat = out['materials'][prim['material']]; self.assertEqual(mat['pbrMetallicRoughness']['baseColorTexture']['index'], 1)
            view = out['bufferViews'][out['images'][1]['bufferView']]
            self.assertEqual(bytes(composed.binary[view['byteOffset']:view['byteOffset'] + view['byteLength']]), image)
            broken = copy.deepcopy(d); broken['extensionsUsed'] = ['KHR_draco_mesh_compression']
            with self.assertRaises(ValueError): composed.append_definition('bad', broken, b)
