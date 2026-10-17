# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Planar patch clipping and embedded glTF UV/colour-space contracts."""
import io,unittest
import numpy as np
from PIL import Image
from cad_texture_patch import replace_planar_rectangle,attach_colour_texture
from export_field_package import GlbWriter
from gltf_scene import accessor
from simplify_package import compact


class TexturePatchTests(unittest.TestCase):
    def source(self):
        return np.array([[-2,-2,0],[2,-2,0],[2,2,0],[-2,2,0]],float),np.array([[0,1,2],[0,2,3]]),np.tile([.42]*3,(2,1))

    def test_rectangle_cut_preserves_outside_area(self):
        p,t,c=self.source();r=replace_planar_rectangle(p,t,c,origin_mm=[0,0,0],axes=np.eye(3),bounds_uv_mm=[-1,-1,1,1]);g=r['positions_mm'][r['triangles']];area=np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).sum()/2;self.assertAlmostEqual(area,12);self.assertAlmostEqual(r['proof']['replaced_area_sum_mm2'],4);self.assertEqual(r['quad_uv'][3].tolist(),[0,0]);self.assertEqual(r['quad_positions_mm'][3].tolist(),[-1,1,0])

    def test_out_of_plane_structure_retained_exactly(self):
        p,t,c=self.source();p[:,2]=1;r=replace_planar_rectangle(p,t,c,origin_mm=[0,0,0],axes=np.eye(3),bounds_uv_mm=[-1,-1,1,1]);np.testing.assert_array_equal(r['positions_mm'][r['triangles']],p[t]);self.assertEqual(r['proof']['removed_input_triangle_indices'],[])

    def test_png_uv_and_linear_factor_survive_compaction(self):
        p,t,c=self.source();w=GlbWriter('test',{'version':'2.0'});w.add_node('member',p/1000,t,['.42,.42,.42']*2);doc={'nodes':w.nodes,'meshes':w.meshes,'materials':w.materials,'accessors':w.accessors,'bufferViews':w.buffer_views,'buffers':[{'byteLength':len(w.bin)}]};png=io.BytesIO();Image.fromarray(np.array([[[255,0,0],[0,255,0]],[[0,0,255],[255,255,255]]],np.uint8)).save(png,format='PNG');uv=np.array([[0,1],[1,1],[1,0],[0,0]],float);blob=attach_colour_texture(doc,w.bin,node_index=0,positions_m=p/1000,triangles=t,uv=uv,png_bytes=png.getvalue());blob=compact(doc,blob);prim=doc['meshes'][doc['nodes'][0]['mesh']]['primitives'][-1];np.testing.assert_array_equal(accessor(doc,blob,prim['attributes']['TEXCOORD_0']),uv);self.assertEqual(doc['materials'][prim['material']]['pbrMetallicRoughness']['baseColorFactor'],[1,1,1,1]);v=doc['bufferViews'][doc['images'][0]['bufferView']];self.assertEqual(blob[v['byteOffset']:v['byteOffset']+v['byteLength']],png.getvalue());self.assertEqual(doc['samplers'][0]['wrapS'],33071)

    def test_invalid_frame_and_material_shape(self):
        p,t,c=self.source()
        with self.assertRaises(ValueError):replace_planar_rectangle(p,t,c,origin_mm=[0,0,0],axes=-np.eye(3),bounds_uv_mm=[-1,-1,1,1])
        with self.assertRaises(ValueError):replace_planar_rectangle(p,t,c[:1],origin_mm=[0,0,0],axes=np.eye(3),bounds_uv_mm=[-1,-1,1,1])

if __name__=='__main__':unittest.main()
