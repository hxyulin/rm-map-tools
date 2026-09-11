import io
import unittest
import numpy as np
from PIL import Image
from gltf_scene import accessor
from attach_texture_atlas import attach


class AttachAtlasTests(unittest.TestCase):
    def fixture(self):
        stream=io.BytesIO()
        Image.new('RGBA',(8,8),(255,255,255,255)).save(stream,format='PNG')
        doc=dict(asset={'version':'2.0'},scene=0,scenes=[{'nodes':[0]}],
                 nodes=[{'name':'root','children':[1],'translation':[2,3,4]}, {'name':'word'}],
                 meshes=[],materials=[],accessors=[],bufferViews=[])
        patch=dict(node='word',page=0,double_sided=True,
                   corners_node_m=[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
                   uv_corners=[[0,0],[1,0],[1,1],[0,1]])
        return doc,stream.getvalue(),patch

    def test_native_payload_uvs_geometry_and_parent(self):
        doc,png,patch=self.fixture()
        out,binary=attach(doc,b'',[png],[patch])
        self.assertNotIn('mesh',doc['nodes'][1])
        self.assertEqual(out['nodes'][0]['translation'],[2,3,4])
        pr=out['meshes'][out['nodes'][1]['mesh']]['primitives'][0]
        np.testing.assert_allclose(accessor(out,binary,pr['attributes']['TEXCOORD_0']),patch['uv_corners'])
        self.assertEqual(accessor(out,binary,pr['indices']).tolist(),[0,1,2,0,2,3])
        np.testing.assert_allclose(accessor(out,binary,pr['attributes']['POSITION'])[:,2],0.0005)
        image=out['images'][0]; view=out['bufferViews'][image['bufferView']]
        self.assertEqual(binary[view['byteOffset']:view['byteOffset']+view['byteLength']],png)
        material=out['materials'][pr['material']]
        self.assertEqual(material['pbrMetallicRoughness']['baseColorTexture']['index'],0)
        self.assertEqual(material['alphaMode'],'MASK')
        self.assertTrue(material['doubleSided'])
        self.assertTrue(all(v['byteOffset']%4==0 for v in out['bufferViews']))
        with self.assertRaises(ValueError): attach(out,binary,[png],[patch])

    def test_bad_anchor_and_offset_fail(self):
        doc,png,patch=self.fixture()
        with self.assertRaises(ValueError): attach(doc,b'',[png],[dict(patch,node='absent')])
        with self.assertRaises(ValueError): attach(doc,b'',[png],[patch],offset_m=-1)

if __name__ == '__main__': unittest.main()
