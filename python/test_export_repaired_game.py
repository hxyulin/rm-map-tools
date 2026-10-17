# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Runtime partitions preserve poses, sharing and exact embedded artwork."""
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from export_repaired_game import partition, collision_scene, export
from gltf_scene import accessor, mesh_instances, write_glb
from simplify_package import append_accessor, scene_triangles
from plan_cad_lods import digest
from test_cad_collision_proxy import cube


def fixture():
    p, t = cube(); p /= 1000; blob = bytearray()
    d = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
         'nodes': [{'children': [1, 2], 'translation': [10, 0, 0]},
                   {'mesh': 0, 'translation': [1, 0, 0]}, {'mesh': 0, 'translation': [0, 2, 0]}],
         'meshes': [], 'materials': [{'pbrMetallicRoughness': {'baseColorTexture': {'index': 1}}}, {'pbrMetallicRoughness': {'baseColorFactor': [1, 0, 0, 1]}}],
         'accessors': [], 'bufferViews': [], 'buffers': [], 'textures': [{'source': 0}, {'source': 1}], 'images': [], 'samplers': []}
    position = append_accessor(d, blob, p.astype(np.float32), 'VEC3', 5126)
    indices = append_accessor(d, blob, t.ravel().astype(np.uint32), 'SCALAR', 5125)
    d['meshes'] = [{'primitives': [{'attributes': {'POSITION': position}, 'indices': indices, 'material': 0}]}]
    images = []
    for color in [(1, 2, 3), (17, 87, 193)]:
        image = io.BytesIO(); Image.new('RGB', (2, 2), color).save(image, format='PNG'); data = image.getvalue()
        blob.extend(b'\0' * (-len(blob) % 4)); offset = len(blob); blob.extend(data)
        d['images'].append({'bufferView': len(d['bufferViews']), 'mimeType': 'image/png'})
        d['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data)}); images.append(data)
    d['buffers'] = [{'byteLength': len(blob)}]
    return d, bytes(blob), images


class GameExportTests(unittest.TestCase):
    def test_partition_keeps_instances_and_prunes_only_unused_artwork(self):
        d, b, images = fixture(); before = copy.deepcopy(d)
        actual, blob = partition(d, b, {1, 2})
        self.assertEqual(d, before); self.assertEqual(len(actual['meshes']), 1)
        self.assertEqual(scene_triangles(actual), 24)
        parts = list(mesh_instances(actual, blob))
        np.testing.assert_allclose(parts[0][2].min(0), [1, 0, 0])
        np.testing.assert_allclose(parts[1][2].min(0), [0, 2, 0])
        self.assertEqual(len(actual['materials']), 1); self.assertEqual(len(actual['images']), 1)
        self.assertEqual(actual['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index'], 0)
        view = actual['bufferViews'][actual['images'][0]['bufferView']]
        self.assertEqual(blob[view['byteOffset']:view['byteOffset'] + view['byteLength']], images[1])

    def test_canonical_root_drops_only_its_placement(self):
        d, b, _ = fixture(); actual, blob = partition(d, b, {1}, root=1)
        self.assertEqual(scene_triangles(actual), 12)
        np.testing.assert_allclose(next(mesh_instances(actual, blob))[2].min(0), [0, 0, 0])
        self.assertEqual(len(actual['nodes']), 1)

    def test_empty_partition_is_rejected(self):
        d, b, _ = fixture()
        with self.assertRaises(ValueError): partition(d, b, set())

    def test_collision_omits_visual_only_component_and_checks_hashes(self):
        d, b, _ = fixture()
        d['nodes'][0].pop('translation'); d['nodes'][1]['extras'] = {'component_id': 'solid'}
        d['nodes'][2]['extras'] = {'component_id': 'marking'}
        template, payload = partition(d, b, {1}, root=1)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); target = root / 'solid.glb'; write_glb(target, template, payload)
            ledger = {'components': [{'id': 'solid', 'collision_method': 'visual-derived fallback', 'visual_glb': 'solid.glb', 'visual_sha256': digest(target)},
                                     {'id': 'marking', 'collision_method': 'visual-only marking'}],
                      'totals': {'collision_budget_placed': 12}}
            with patch('export_repaired_game.ROOT', root):
                result, _, inputs = collision_scene(d, ledger)
                self.assertEqual(scene_triangles(result), 12)
                ledger['components'][0]['visual_sha256'] = 'wrong'
                with self.assertRaises(ValueError): collision_scene(d, ledger)

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): export(folder)


if __name__ == '__main__': unittest.main()
