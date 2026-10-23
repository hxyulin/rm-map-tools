# SPDX-License-Identifier: MIT OR Apache-2.0
"""Primitive transforms and hybrid replacement accounting, independent of arena data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial.transform import Rotation
from collision_shape_export import cylinder_in_scene, digest, export, z_rotation
from gltf_scene import read_glb, write_glb
from simplify_package import append_accessor


def fixture(path):
    doc={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],
         'nodes':[{'name':'root','children':[1,2],'translation':[1,2,3],'rotation':Rotation.from_euler('x',.7).as_quat().tolist(),'extras':{'component_id':'test/arm'}},
                  {'name':'replace','mesh':0},{'name':'retain-shared-mesh','mesh':0}],
         'materials':[{'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1]}}],
         'meshes':[], 'accessors':[], 'bufferViews':[], 'buffers':[{'byteLength':0}]}
    blob=bytearray();p=np.array([[0.,0,0],[1,0,0],[0,1,0]],dtype=np.float32)
    pr={'attributes':{'POSITION':append_accessor(doc,blob,p,'VEC3',5126)},'indices':append_accessor(doc,blob,np.array([0,1,2],dtype=np.uint32),'SCALAR',5125),'material':0}
    doc['meshes']=[{'primitives':[pr]}];doc['buffers'][0]['byteLength']=len(blob);write_glb(path,doc,blob)


def params():return {'center_m':[.1,.2,.3],'axis_unit_vector':[0.,0,1.],'radius_m':.04,'length_m':.3,'solid':True}


class CollisionShapeExportTests(unittest.TestCase):
    def test_axis_quaternion_all_directions(self):
        for axis in [[0,0,1],[0,0,-1],[1,0,0],[0,1,0],[.6,0,.8]]:
            np.testing.assert_allclose(Rotation.from_quat(z_rotation(axis)).apply([0,0,1]),axis,atol=1e-12)

    def test_rotated_scaled_center_and_endpoints(self):
        rot=Rotation.from_euler('xyz',[.3,-.8,.2]).as_matrix();world=np.eye(4);world[:3,:3]=rot*2;world[:3,3]=[1,2,3]
        source=params();actual=cylinder_in_scene(source,world)
        np.testing.assert_allclose(actual['pose']['translation_m'],rot@np.array(source['center_m'])*2+[1,2,3])
        np.testing.assert_allclose(Rotation.from_quat(actual['pose']['rotation_xyzw']).apply([0,0,1]),rot[:,2],atol=1e-12)
        self.assertAlmostEqual(actual['radius_m'],.08);self.assertAlmostEqual(actual['length_m'],.6)

    def test_reject_hollow_bad_axis_and_dimensions(self):
        for patch in [{'solid':False},{'axis_unit_vector':[0,0,2]},{'radius_m':0},{'length_m':float('nan')}]:
            with self.assertRaises(ValueError):cylinder_in_scene({**params(),**patch},np.eye(4))

    def test_reject_nonuniform_shear_reflection(self):
        for linear in [np.diag([1.,2,1]),np.array([[1,.1,0],[0,1,0],[0,0,1]]),np.diag([-1.,1,1])]:
            world=np.eye(4);world[:3,:3]=linear
            with self.assertRaises(ValueError):cylinder_in_scene(params(),world)

    def test_hybrid_removes_only_selected_shared_instance_and_sdf_roundtrips(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);source=root/'source.glb';fixture(source)
            selection={'source_sha256':digest(source),'asset_id':'test','replacements':[{'node_index':1,'node_name':'replace','cylinder':params()}]}
            result=export(source,selection,root/'out');self.assertEqual(result['removed_mesh_triangles'],1);self.assertEqual(result['retained_mesh']['triangles'],1)
            d,_=read_glb(root/'out/remainder.glb');self.assertNotIn('mesh',d['nodes'][1]);self.assertIn('mesh',d['nodes'][2]);self.assertEqual(digest(source),selection['source_sha256'])
            self.assertEqual(result['native_parts'][0]['component_id'],'test/arm')
            sdf=ET.parse(root/'out/model.sdf');cols=sdf.findall('.//collision');self.assertEqual(len(cols),2);self.assertEqual(len(sdf.findall('.//cylinder')),1)
            pose=np.fromstring(cols[1].findtext('pose'),sep=' ');shape=result['native_parts'][0]['shape']
            np.testing.assert_allclose(pose[:3],shape['pose']['translation_m']);np.testing.assert_allclose(Rotation.from_euler('xyz',pose[3:]).as_matrix(),Rotation.from_quat(shape['pose']['rotation_xyzw']).as_matrix(),atol=1e-12)
            self.assertEqual(float(cols[1].findtext('geometry/cylinder/length')),shape['length_m'])
            self.assertTrue((root/'out'/cols[0].findtext('geometry/mesh/uri')).is_file())
            self.assertEqual(json.loads((root/'out/collision-shapes.json').read_text()),result)

    def test_multiple_cylinders_replace_one_node_once(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);source=root/'source.glb';fixture(source)
            selection={'source_sha256':digest(source),'asset_id':'test','replacements':[{'node_index':1,'node_name':'replace','cylinders':[params(),{**params(),'radius_m':.02}]}]}
            result=export(source,selection,root/'out')
            self.assertEqual(result['removed_mesh_triangles'],1)
            self.assertEqual(result['retained_mesh']['triangles'],1)
            self.assertEqual(len(result['native_parts']),2)
            self.assertEqual(len({p['id']for p in result['native_parts']}),2)
            self.assertEqual(len(ET.parse(root/'out/model.sdf').findall('.//cylinder')),2)

    def test_bad_identity_duplicate_selection_and_source_hash_fail_before_write(self):
        with tempfile.TemporaryDirectory()as td:
            root=Path(td);source=root/'source.glb';fixture(source);row={'node_index':1,'node_name':'replace','cylinder':params()}
            cases=[{'source_sha256':'0'*64,'replacements':[row]}, {'source_sha256':digest(source),'replacements':[{**row,'node_name':'wrong'}]}, {'source_sha256':digest(source),'replacements':[row,row]}]
            for i,case in enumerate(cases):
                out=root/str(i)
                with self.assertRaises(ValueError):export(source,{'asset_id':'test',**case},out)
                self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
