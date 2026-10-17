# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Written coverage repairs preserve source attributes, images and shared nodes."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from export_repaired_game import dump
from gltf_scene import accessor, read_glb, write_glb
from guard_repaired_game import guard
from plan_cad_lods import digest
from simplify_package import append_accessor
from test_export_repaired_game import fixture


class GuardExportTests(unittest.TestCase):
    def test_written_repair_restores_cube_and_preserves_instances_and_artwork(self):
        d, b, _ = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'out/rmuc2027-equipment-shells/candidate-field.glb'
            source.parent.mkdir(parents=True); write_glb(source, d, b); before = digest(source)
            low = root / 'out/rmuc2027-low-repair/budget-sealed-field.glb'
            low.parent.mkdir(); ld = copy.deepcopy(d); blob = bytearray(b)
            prim = ld['meshes'][0]['primitives'][0]
            faces = accessor(d, b, prim['indices']).reshape(-1, 3)[:1]
            prim['indices'] = append_accessor(ld, blob, faces.ravel().astype(np.uint32), 'SCALAR', 5125)
            prim['extras'] = {'source_mesh_index': 0, 'source_primitive_index': 0}
            write_glb(low, ld, blob)
            dump(low.parent / 'budget-sealed.json', {'sha256': digest(low)})
            dump(low.parent / 'seal-plan.json', {'source_sha256': digest(source)})
            out = root / 'guarded'
            with patch('guard_repaired_game.ROOT', root): guard(out)
            actual, ab = read_glb(out / 'guarded-field.glb')
            self.assertEqual(actual['nodes'], d['nodes'])
            self.assertEqual(actual['materials'], d['materials'])
            for old_image, new_image in zip(d['images'], actual['images']):
                ov = d['bufferViews'][old_image['bufferView']]; nv = actual['bufferViews'][new_image['bufferView']]
                self.assertEqual(b[ov['byteOffset']:ov['byteOffset'] + ov['byteLength']],
                                 ab[nv['byteOffset']:nv['byteOffset'] + nv['byteLength']])
            p = actual['meshes'][0]['primitives'][0]
            self.assertEqual(len(accessor(actual, ab, p['indices'])), 36)
            old = d['meshes'][0]['primitives'][0]
            np.testing.assert_equal(accessor(actual, ab, p['attributes']['POSITION'])[accessor(actual, ab, p['indices'])],
                                    accessor(d, b, old['attributes']['POSITION'])[accessor(d, b, old['indices'])])
            self.assertEqual(digest(source), before)
            with patch('guard_repaired_game.ROOT', root), self.assertRaises(ValueError): guard(out)


if __name__ == '__main__': unittest.main()
