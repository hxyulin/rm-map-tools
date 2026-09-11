# SPDX-License-Identifier: MIT OR Apache-2.0
import tempfile
import unittest
from pathlib import Path

import numpy as np
from classify_decorations import classify
from collision_artwork import strip
from export_field_package import GlbWriter
from gltf_scene import read_glb, mesh_instances


class DecorationTests(unittest.TestCase):
    def test_elevated_wall_text_preserves_visual_and_backing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'fixture.glb'
            writer = GlbWriter('root', {'version': '2.0'})
            points = np.array([[0., 0, 3], [0, 1, 3], [0, 0, 4]])
            writer.add_node('text', points, np.array([[0, 1, 2]]), ['1,1,1'])
            writer.add_node('wall', points + [-.01, 0, 0], np.array([[0, 1, 2]]), ['0,0,0'])
            writer.write(path)
            doc, binary = read_glb(path)
            doc['nodes'].append(dict(name='shared', mesh=doc['nodes'][1]['mesh']))
            doc['nodes'][0]['children'].append(3)
            selections = [dict(node='text', material='colour_1,1,1', kind='text')]
            visual, records = classify(doc, binary, selections)
            for old, new in zip(mesh_instances(doc, binary), mesh_instances(visual, binary)):
                np.testing.assert_array_equal(old[2], new[2])
                np.testing.assert_array_equal(old[3], new[3])
            primitive = visual['meshes'][visual['nodes'][1]['mesh']]['primitives'][0]
            self.assertEqual(primitive['extras']['rm']['layer'], 'decoration')
            self.assertFalse(primitive['extras']['rm']['collision'])
            shared = visual['meshes'][visual['nodes'][3]['mesh']]['primitives'][0]
            self.assertNotIn('rm', shared.get('extras', {}))
            collision, packed, _ = strip(doc, binary, [dict(node='text', material='colour_1,1,1')])
            self.assertEqual([collision['nodes'][i]['name'] for i, *_ in mesh_instances(collision, packed)], ['wall', 'shared'])
            with self.assertRaises(ValueError):
                classify(doc, binary, selections * 2)
            with self.assertRaises(ValueError):
                classify(doc, binary, [dict(selections[0], node='missing')])


if __name__ == '__main__':
    unittest.main()
