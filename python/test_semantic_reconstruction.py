# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from export_semantics import digest, transform_asset
from gltf_scene import mesh_instances, write_glb
from semantic_reconstruction import add_reconstruction, tapered_prism
from test_gltf_scene import fixture


class ReconstructionTests(unittest.TestCase):
    def test_tapered_housing_is_closed_and_outward_wound(self):
        p, _, t = tapered_prism({'sides': 3, 'z_range_m': [.3, .8],
                                'radius_m': [.2, .1], 'center_xy_m': [0, 0]})
        volume = np.einsum('ij,ij->i', p[t[:, 0]], np.cross(p[t[:, 1]], p[t[:, 2]])).sum()/6
        self.assertGreater(volume, 0)
        _, remap = np.unique(np.round(p, 9), axis=0, return_inverse=True)
        faces = remap[t]
        edges = np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        np.testing.assert_array_equal(counts, 2)

    def test_donor_instances_preserve_original_mesh_and_are_labelled(self):
        doc, binary = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_glb(root/'donor.glb', doc, binary)
            source = {'file': 'donor.glb', 'sha256': digest(root/'donor.glb'), 'select': {'name': 'plate'}}
            spec = {'id': 'assembly', 'nodes': [], 'geometry_additions': []}
            for i in range(2):
                matrix = np.eye(4); matrix[2, 3] = i+3
                spec['geometry_additions'].append({'type': 'copy_mesh', 'source': source,
                    'name': f'rebuilt/{i}', 'parent': {'name': 'root'},
                    'matrix': matrix.flatten(order='F').tolist(),
                    'metadata': {'id': f'rebuilt.{i}', 'roles': ['armor_module'], 'layer': 'reconstruction'},
                    'evidence': ['synthetic reused part']})
            out, data, resolved = add_reconstruction(doc, binary, spec, root)
            out, bindings = transform_asset(out, resolved, 'hash')
            meshes = {i: (x, t) for i, _, x, t, _ in mesh_instances(out, data)}
            original = {i: (x, t) for i, _, x, t, _ in mesh_instances(doc, binary)}
            for i in original:
                np.testing.assert_array_equal(meshes[i][0], original[i][0])
                np.testing.assert_array_equal(meshes[i][1], original[i][1])
            np.testing.assert_allclose(meshes[3][0], [[11, 0, 3], [12, 0, 3], [11, 1, 3]])
            self.assertEqual(out['nodes'][3]['mesh'], out['nodes'][4]['mesh'])
            self.assertEqual(bindings['nodes'][0]['metadata']['geometry_origin'], 'reconstruction')
            self.assertEqual(len(doc['nodes']), 3)
            bad = copy.deepcopy(spec)
            bad['geometry_additions'][0]['source']['sha256'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'checksum'):
                add_reconstruction(doc, binary, bad, root)
            bad = copy.deepcopy(spec)
            bad['geometry_additions'][0]['source']['file'] = '../outside.glb'
            with self.assertRaisesRegex(ValueError, 'outside'):
                add_reconstruction(doc, binary, bad, root)

    def test_additions_cannot_masquerade_as_original_geometry(self):
        doc, binary = fixture()
        spec = {'geometry_additions': [{'type': 'tapered_prism', 'name': 'inner',
                'parent': {'name': 'root'}, 'metadata': {'id': 'inner', 'layer': 'geometry'},
                'evidence': ['fixture']}]}
        with self.assertRaisesRegex(ValueError, 'own layer'):
            add_reconstruction(doc, binary, spec, '.')
