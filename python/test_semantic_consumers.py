# SPDX-License-Identifier: MIT OR Apache-2.0
from pathlib import Path
import tempfile
import unittest

import numpy as np

from export_sim import Asset
from export_semantics import transform_asset
from gltf_scene import write_glb
from test_gltf_scene import fixture
from test_semantics import rules


class ConsumerTests(unittest.TestCase):
    def test_semantic_assets_require_explicit_static_pose(self):
        with self.assertRaisesRegex(ValueError, 'static-rest-pose'):
            Asset('test', {'semantics': {'file': 'articulation.json'}}, '/unused')

    def test_static_pose_bakes_nested_transforms(self):
        document, binary = fixture()
        document, _ = transform_asset(document, rules(), 'hash')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            write_glb(path / 'mesh.glb', document, binary)
            entry = {'visual': 'mesh.glb', 'collision': 'mesh.glb',
                     'semantics': {'file': 'articulation.json'}}
            asset = Asset('example', entry, directory, static_rest_pose=True)
            np.testing.assert_allclose(asset.bbox_local[0], [11, 0, 0])
            np.testing.assert_allclose(asset.bbox_local[1], [12, 3, 1])
            self.assertEqual(sum(len(t) for _, _, t in asset.colours), 2)


if __name__ == '__main__':
    unittest.main()
