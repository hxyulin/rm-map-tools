import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from export_field_package import GlbWriter
from gltf_scene import read_glb, mesh_instances
from texture_atlas import bake, export_atlas


class AtlasTests(unittest.TestCase):
    def fixture(self, root):
        writer = GlbWriter('root', {'version': '2.0'})
        p = np.array([[0.,0,0],[1,0,0],[0,1,0]])
        writer.add_node('letter', p, np.array([[0,1,2]]), ['1,1,1'])
        writer.add_node('hardware', p+2, np.array([[0,1,2]]), ['0,0,0'])
        writer.write(root/'visual.glb')
        return read_glb(root/'visual.glb')

    def test_bake_removes_only_selected_geometry_and_records_uvs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc, binary = self.fixture(root)
            out, packed, pages, records = bake(doc, binary, [{'node':'letter','material':'colour_1,1,1'}], 32, 128)
            self.assertEqual(len(list(mesh_instances(out, packed))), 1)
            self.assertLess(len(packed), len(binary))
            self.assertNotIn('mesh', out['nodes'][1])
            self.assertIn('mesh', doc['nodes'][1])
            self.assertGreater(np.asarray(pages[0])[:,:,3].max(), 0)
            self.assertEqual(np.asarray(pages[0])[0,0,3], 0)
            corners = np.array(records[0]['corners_node_m'])
            self.assertTrue(np.allclose(corners[:,2], 0))
            self.assertTrue(np.all((np.array(records[0]['uv_corners']) >= 0) & (np.array(records[0]['uv_corners']) <= 1)))

    def test_unmatched_duplicate_and_oversize_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, binary = self.fixture(Path(tmp))
            sel = {'node':'letter','material':'colour_1,1,1'}
            for selections in [[dict(sel,node='missing')],[sel,sel]]:
                with self.assertRaises(ValueError): bake(doc,binary,selections,32,128)
            with self.assertRaises(ValueError): bake(doc,binary,[sel],1024,16)

    def test_nonplanar_selection_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = GlbWriter('root', {'version': '2.0'})
            writer.add_node('solid', np.array([[0.,0,0],[1,0,0],[0,1,0],[0,0,1]]),
                            np.array([[0,1,2],[0,1,3]]), ['1,1,1']*2)
            writer.write(root/'solid.glb')
            doc, binary = read_glb(root/'solid.glb')
            with self.assertRaisesRegex(ValueError, 'not planar'):
                bake(doc, binary, [{'node':'solid','material':'colour_1,1,1'}])

    def test_grouping_uses_parent_frame_and_preserves_spacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            writer = GlbWriter('root', {'version': '2.0'})
            points = np.array([[0.,0,0],[0.1,0,0],[0.1,0.2,0],[0,0.2,0]])
            for name in ['A', 'B']:
                writer.add_node(name, points, np.array([[0,1,2],[0,2,3]]), ['1,1,1']*2)
            writer.write(root/'letters.glb')
            doc, binary = read_glb(root/'letters.glb')
            doc['nodes'][0]['translation'] = [10,20,30]
            doc['nodes'][2]['translation'] = [0.15,0,0]
            selections = [dict(node=name,material='colour_1,1,1') for name in ['A','B']]
            out, packed, pages, records = bake(doc,binary,selections,100,128,merge_distance=0.06)
            self.assertEqual(len(records),1)
            self.assertEqual(len(records[0]['sources']),2)
            self.assertEqual(records[0]['source_triangles'],4)
            corners=np.array(records[0]['corners_node_m'])
            np.testing.assert_allclose(corners.min(0),[0,0,0],atol=1e-7)
            np.testing.assert_allclose(corners.max(0),[0.25,0.2,0],atol=1e-7)
            self.assertEqual(out['nodes'][0]['translation'],[10,20,30])
            self.assertEqual(len(list(mesh_instances(out,packed))),0)
            x,y,w,h=records[0]['rect_px']
            alpha=np.asarray(pages[0])[:,:,3]
            self.assertGreater(alpha[y+h//2,x+5],200)
            self.assertLess(alpha[y+h//2,x+12],10)
            self.assertGreater(alpha[y+h//2,x+20],200)
            # Nearby but noncoplanar letters cannot share a patch.
            doc['nodes'][2]['translation'][2] = 0.02
            self.assertEqual(len(bake(doc,binary,selections,100,128,merge_distance=0.06)[3]),2)
            # Different assembly parents must remain separate, even at identical positions.
            doc['nodes'][2]['translation'][2] = 0
            doc['nodes'].append({'name':'assembly','children':[2]})
            doc['nodes'][0]['children']=[1,3]
            self.assertEqual(len(bake(doc,binary,selections,100,128,merge_distance=0.06)[3]),2)

    def test_normal_hint_places_thick_artwork_at_frontmost_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            writer=GlbWriter('root',{'version':'2.0'})
            points=np.array([[0.,0,0],[1,0,0],[0,1,0],[0,0,.004],[1,0,.004],[0,1,.004]])
            writer.add_node('paint',points,np.array([[0,2,1],[3,5,4]]),['1,1,1']*2)
            writer.write(root/'paint.glb')
            doc,binary=read_glb(root/'paint.glb')
            _,_,_,patches=bake(doc,binary,[dict(node='paint',material='colour_1,1,1')],32,128,normal_hint=[0,0,1])
            corners=np.array(patches[0]['corners_node_m'])
            np.testing.assert_allclose(corners[:,2],.004,atol=1e-7)
            self.assertGreater(np.cross(corners[1]-corners[0],corners[3]-corners[0])[2],0)

    def test_embedded_pipeline_simplifies_before_attaching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.fixture(root)
            (root/'manifest.json').write_text(json.dumps({'assets':{'art':{'visual':'visual.glb','triangles':2}}}))
            rules=root/'rules.json'
            rules.write_text(json.dumps({'schema_version':1,'render_mode':'embedded',
                'pixels_per_metre':32,'atlas_size':128,
                'files':{'visual.glb':[{'node':'letter','material':'colour_1,1,1'}]},
                'simplify':{'visual.glb':{'error_mm':1}}}))
            sidecar=export_atlas(root,rules)
            self.assertEqual(sidecar['files']['visual.glb']['backing_simplification']['before_triangles'],1)
            doc,binary=read_glb(root/'visual.glb')
            self.assertEqual(sum(len(t) for _,_,_,t,_ in mesh_instances(doc,binary)),3)
            self.assertEqual(len(doc['images']),1)

    def test_pipeline_removes_collider_artwork_without_adding_texture_quads(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.fixture(root)
            (root/'collision.glb').write_bytes((root/'visual.glb').read_bytes())
            checksum=hashlib.sha256((root/'collision.glb').read_bytes()).hexdigest()
            (root/'manifest.json').write_text(json.dumps({'assets':{'art':{
                'visual':'visual.glb','collision':'collision.glb','collision_sha256':checksum,'triangles':2}}}))
            rules=root/'rules.json'
            rules.write_text(json.dumps({'schema_version':1,'render_mode':'embedded',
                'pixels_per_metre':32,'atlas_size':128,
                'files':{'visual.glb':[{'node':'letter','material':'colour_1,1,1'}]},
                'simplify':{'visual.glb':{'error_mm':1}},
                'collision_simplify':{'visual.glb':{'error_mm':1}}}))
            export_atlas(root,rules)
            manifest=json.loads((root/'manifest.json').read_text())
            self.assertEqual(manifest['assets']['art']['collision_triangles'],1)
            self.assertEqual(manifest['assets']['art']['triangles'],3)
            doc,_=read_glb(root/'collision.glb')
            self.assertNotIn('images',doc)
            self.assertEqual(manifest['assets']['art']['collision_artwork_removed']['removed_triangles'],1)

    def test_package_manifest_and_collision_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.fixture(root)
            (root/'collision.glb').write_bytes((root/'visual.glb').read_bytes())
            original=(root/'collision.glb').read_bytes()
            (root/'manifest.json').write_text(json.dumps({'assets':{'art':{'visual':'visual.glb','collision':'collision.glb','triangles':2}}}))
            rules=root/'rules.json'
            rules.write_text(json.dumps({'schema_version':1,'pixels_per_metre':32,'atlas_size':128,'files':{'visual.glb':[{'node':'letter','material':'colour_1,1,1'}]}}))
            export_atlas(root,rules)
            self.assertEqual((root/'collision.glb').read_bytes(),original)
            self.assertEqual(json.loads((root/'manifest.json').read_text())['assets']['art']['triangles'],1)
            self.assertTrue((root/'texture-atlas.json').exists())
            from attach_texture_atlas import attach_package
            attach_package(root)
            manifest=json.loads((root/'manifest.json').read_text())
            self.assertEqual(manifest['assets']['art']['triangles'],3)
            self.assertTrue(manifest['texture_atlas']['embedded'])
            doc,binary=read_glb(root/'visual.glb')
            self.assertEqual(sum(len(t) for _,_,_,t,_ in mesh_instances(doc,binary)),3)
            self.assertEqual(len(doc['images']),1)
            self.assertNotIn('uri',doc['images'][0])

if __name__ == '__main__': unittest.main()
