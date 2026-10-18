# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""CAD reference cleanup preserves real modules, shared meshes and source bytes."""
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np
from export_field_package import GlbWriter
from gltf_scene import read_glb, mesh_instances
from robot_reference_geometry import apply_reference_exclusions, verify_reference_cleanup, compact_reference_resources


class ReferenceCleanupTests(unittest.TestCase):
    def fixture(self):
        box = np.array([[x, y, z] for x in [0., .1] for y in [0., .1] for z in [0., .1]])
        faces = np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],
                          [2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]])
        cone = np.array([[1.,1.,1.],[2.,1.,1.],[1.,2.,1.],[1.,1.,2.]])
        points = np.concatenate([box, cone])
        triangles = np.concatenate([faces, np.array([[8,9,10],[8,11,9],[8,10,11],[9,11,10]])])
        writer = GlbWriter('fixture', {'version': '2.0'})
        writer.add_node('module-with-helper', points, triangles, [None]*len(triangles),
                        extras={'native_solid_index': 0, 'source_leaf_path': '1/1'})
        writer.add_node('unselected-identical-geometry', points, triangles, [None]*len(triangles),
                        extras={'native_solid_index': 7})
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary)/'fixture.glb'
            writer.write(p)
            document, binary = read_glb(p)
        rows = [{'path': '1/1', 'name': 'module mounting requirements', 'native_solids': []},
                {'path': '1/2', 'name': 'mechanical part', 'native_solids': [7]}]
        rule = {'path': '1/1', 'expected_name': 'module mounting requirements', 'reason': 'reviewed reference cone',
                'expected_triangles': 4, 'extent_mm': [1000,1000,1000]}
        return document, binary, rows, rule

    def test_component_removal_keeps_hardware_and_does_not_change_shared_instance(self):
        d, b, rows, rule = self.fixture()
        original=copy.deepcopy(d)
        before = list(mesh_instances(d,b))
        materials = copy.deepcopy(d['materials'])
        attributes = copy.deepcopy(d['meshes'][d['nodes'][1]['mesh']]['primitives'][0]['attributes'])
        self.assertEqual(d['nodes'][1]['mesh'], d['nodes'][2]['mesh'])
        payload, report = apply_reference_exclusions(d,b,rows,[rule])
        after = list(mesh_instances(d,payload))
        self.assertEqual(report[0]['removed_triangles'],4)
        checked=verify_reference_cleanup(original,b,d,payload,report)
        self.assertTrue(checked['retained_vertex_attributes_exact'])
        broken=copy.deepcopy(d)
        broken['nodes'][2]['translation']=[1,0,0]
        with self.assertRaisesRegex(ValueError, 'moved'):
            verify_reference_cleanup(original,b,broken,payload,report)
        self.assertEqual(len(after[0][3]),12)
        self.assertEqual(len(after[1][3]),16)
        self.assertEqual(payload[:len(b)],b)
        self.assertEqual(d['materials'],materials)
        primitive = d['meshes'][d['nodes'][1]['mesh']]['primitives'][0]
        self.assertEqual(primitive['attributes'], attributes)
        np.testing.assert_array_equal(after[1][2][after[1][3]],before[1][2][before[1][3]])
        np.testing.assert_array_equal(after[0][2][after[0][3]],before[0][2][before[0][3]][:12])

    def test_only_explicitly_selected_solid_is_removed_and_anchor_survives(self):
        d,b,rows,_ = self.fixture()
        rule={'path':'1/2','expected_name':'mechanical part','solid':7,'expected_triangles':16,
              'reason':'explicit reviewed fixture selection'}
        payload,report=apply_reference_exclusions(d,b,rows,[rule])
        self.assertEqual(payload,b)
        self.assertNotIn('mesh',d['nodes'][2])
        self.assertIn('mesh',d['nodes'][1])
        self.assertIn('reference_geometry_excluded',d['nodes'][2]['extras'])
        self.assertEqual(report[0]['removed_triangles'],16)

    def test_unknown_name_or_changed_component_fails_closed(self):
        for key,value in [('expected_name','different'),('expected_triangles',5),('extent_mm',[900,1000,1000])]:
            d,b,rows,rule=self.fixture()
            rule[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                apply_reference_exclusions(d,b,rows,[rule])

    def test_local_plane_can_remove_attached_helpers_without_dropping_the_solid(self):
        d,b,rows,_=self.fixture()
        rows[1]['placement']=[[1,0,0,0],[0,1,0,0],[0,0,1,0]]
        rule={'path':'1/2','expected_name':'mechanical part','solid':7,'expected_triangles':4,
              'source_local_plane':{'axis':1,'above_mm':500},'reason':'reviewed helper above board'}
        payload,report=apply_reference_exclusions(d,b,rows,[rule],source_center_mm=[0,0,0])
        self.assertEqual(report[0]['retained_triangles'],12)
        self.assertIn('mesh',d['nodes'][2])
        self.assertEqual([len(t) for ni,pi,p,t,m in mesh_instances(d,payload)],[16,12])

    def test_local_plane_uses_audited_rotation_translation_and_cook_center(self):
        d,b,rows,_=self.fixture()
        rows[1]['placement']=[[0,-1,0,0],[1,0,0,-250],[0,0,1,0]]
        rule={'path':'1/2','expected_name':'mechanical part','solid':7,'expected_triangles':4,
              'source_local_plane':{'axis':0,'above_mm':950},'reason':'reviewed local-frame helper'}
        payload,report=apply_reference_exclusions(d,b,rows,[rule],source_center_mm=[0,200,0])
        self.assertEqual(report[0]['retained_triangles'],12)
        self.assertEqual([len(t) for ni,pi,p,t,m in mesh_instances(d,payload)],[16,12])

    def test_compaction_removes_unused_resources_and_preserves_retained_surfaces(self):
        d,b,rows,rule=self.fixture()
        original=copy.deepcopy(d)
        payload,report=apply_reference_exclusions(d,b,rows,[rule])
        # A shared physical instance still needs the original mesh. Add a truly
        # unused view/mesh to ensure compaction drops only unreachable resources.
        d['meshes'].append(copy.deepcopy(d['meshes'][0]))
        d['bufferViews'].append({'buffer':0,'byteOffset':len(payload),'byteLength':64})
        payload += b'junk' * 16
        d['buffers'][0]['byteLength']=len(payload)
        unpruned_size=len(payload)
        payload=compact_reference_resources(d,payload)
        checked=verify_reference_cleanup(original,b,d,payload,report)
        self.assertTrue(checked['retained_vertex_attributes_exact'])
        self.assertLess(len(payload),unpruned_size)
        live={n['mesh'] for n in d['nodes'] if 'mesh' in n}
        self.assertEqual(live,set(range(len(d['meshes']))))

    def test_empty_policy_never_infers_deletion_from_shape_or_name(self):
        d,b,rows,_=self.fixture()
        before=copy.deepcopy(d)
        self.assertEqual(apply_reference_exclusions(d,b,rows,[]),(b,[]))
        self.assertEqual(d,before)


if __name__ == '__main__':
    unittest.main()
