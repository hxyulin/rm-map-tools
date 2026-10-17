# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Visual trial index validity and source attribute preservation."""
import tempfile
import io
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from cad_experimental_lod import coarse_indices, export_trial
from gltf_scene import read_glb, write_glb, accessor
from simplify_package import append_accessor
from test_cad_collision_proxy import cube, subdivide


class ExperimentalLodTests(unittest.TestCase):
    def test_reduction_returns_source_indices_without_mutating_input(self):
        p, t = subdivide(*cube()); before = p.copy(); original = t.copy()
        f = coarse_indices(p, t, .1)
        self.assertGreater(len(f), 0); self.assertLess(len(f), len(t))
        self.assertLess(f.max(), len(p)); np.testing.assert_array_equal(p, before)
        np.testing.assert_array_equal(t, original)

    def test_empty_backend_result_retains_primitive(self):
        p, t = subdivide(*cube())
        with patch('cad_experimental_lod.mo.simplify_sloppy', return_value=0):
            np.testing.assert_array_equal(coarse_indices(p, t, .005), t)

    def test_policy_rejected(self):
        p, t = cube()
        for ratio in [0, -1, 2, float('nan'), float('inf')]:
            with self.assertRaises(ValueError): coarse_indices(p, t, ratio)

    def test_shared_mirrored_nodes_and_textured_attributes_survive_export(self):
        p, t = subdivide(*cube()); blob = bytearray()
        doc = {'asset': {'version': '2.0'}, 'buffers': [], 'bufferViews': [], 'accessors': [],
               'materials': [{'pbrMetallicRoughness': {'baseColorFactor': [.2, .4, .7, 1]}}],
               'meshes': [], 'nodes': [{'mesh': 0, 'translation': [1, 2, 3]},
                                     {'mesh': 0, 'scale': [-1, 1, 1]}],
               'scenes': [{'nodes': [0, 1]}], 'scene': 0}
        attrs = {'POSITION': append_accessor(doc, blob, p.astype(np.float32), 'VEC3', 5126),
                 'TEXCOORD_0': append_accessor(doc, blob, p[:, :2].astype(np.float32), 'VEC2', 5126),
                 'COLOR_0': append_accessor(doc, blob, np.full((len(p), 4), 127, np.uint8), 'VEC4', 5121)}
        doc['accessors'][attrs['COLOR_0']]['normalized'] = True
        indices = append_accessor(doc, blob, t.ravel().astype(np.uint32), 'SCALAR', 5125)
        # Include an orphan mesh before the used definition to exercise compaction.
        doc['meshes'] = [{'primitives': []}, {'primitives': [{'attributes': attrs, 'indices': indices, 'material': 0}]}]
        for n in doc['nodes']: n['mesh'] = 1
        image = io.BytesIO(); Image.new('RGB', (2, 2), (19, 87, 143)).save(image, format='PNG')
        payload = image.getvalue(); blob.extend(b'\0' * (-len(blob) % 4))
        doc['images'] = [{'bufferView': len(doc['bufferViews']), 'mimeType': 'image/png'}]
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(payload)})
        blob.extend(payload); doc['textures'] = [{'source': 0}]
        doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture'] = {'index': 0}
        doc['buffers'] = [{'byteLength': len(blob)}]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.glb'; target = Path(folder) / 'trial.glb'
            write_glb(source, doc, bytes(blob)); original = source.read_bytes()
            report = export_trial(source, target, .1); actual, ab = read_glb(target)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(len(actual['meshes']), 1)
            self.assertEqual([n['mesh'] for n in actual['nodes']], [0, 0])
            self.assertEqual(actual['nodes'][0]['translation'], [1, 2, 3])
            self.assertEqual(actual['nodes'][1]['scale'], [-1, 1, 1])
            self.assertEqual(report['placed_triangles'], 2 * report['stored_triangles'])
            prim = actual['meshes'][0]['primitives'][0]
            self.assertTrue(actual['accessors'][prim['attributes']['COLOR_0']]['normalized'])
            pos = accessor(actual, ab, prim['attributes']['POSITION'])
            np.testing.assert_array_equal(accessor(actual, ab, prim['attributes']['TEXCOORD_0']), pos[:, :2])
            self.assertTrue(report['exported_attributes_verified'])
            view = actual['bufferViews'][actual['images'][0]['bufferView']]
            self.assertEqual(ab[view['byteOffset']:view['byteOffset'] + view['byteLength']], payload)


if __name__ == '__main__': unittest.main()
