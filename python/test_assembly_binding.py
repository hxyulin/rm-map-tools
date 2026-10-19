# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reference geometry preservation and explicit source-rig partition contracts."""
import copy
import importlib.util
from pathlib import Path
import unittest
import numpy as np
from test_gltf_scene import fixture
spec=importlib.util.spec_from_file_location('assembly_binding',Path(__file__).resolve().parents[1]/'benchmarks/2026-10-18-team-robot/bind_assembly.py')
binding=importlib.util.module_from_spec(spec);spec.loader.exec_module(binding)


class AssemblyBindingTests(unittest.TestCase):
    def test_reparenting_preserves_source_vertices_buffers_materials_and_input(self):
        doc,binary=fixture();original=copy.deepcopy(doc)
        frames={'a':binding.transform(np.eye(3),[.3,.1,.2]),'b':binding.transform(np.eye(3),[-.1,.2,.3])}
        convert=binding.transform(binding.C,[.1,-.2,.3])
        out,payload,report=binding.bind(doc,binary,lambda n:'a' if n['name']=='plate' else 'b',convert,frames,'test')
        self.assertEqual(doc,original);self.assertEqual(payload,binary)
        self.assertEqual(out['materials'],doc['materials']);self.assertEqual(out['meshes'],doc['meshes'])
        self.assertEqual(report['retained_source_mesh_nodes'],2);self.assertEqual(report['triangles'],2)
        self.assertLess(report['maximum_reference_vertex_error_m'],1e-12)
    def test_omission_is_explicit_and_unknown_owners_fail(self):
        doc,binary=fixture();frames={'body':np.eye(4)}
        _,_,report=binding.bind(doc,binary,lambda n:'body' if n['name']=='plate' else None,np.eye(4),frames,'test')
        self.assertEqual(report['removed_nodes'],[2]);self.assertEqual(report['triangles'],1)
        with self.assertRaises(ValueError):binding.bind(doc,binary,lambda n:'unknown',np.eye(4),frames,'test')
    def test_rigid_source_subassemblies_and_jaw_ownership_are_distinct(self):
        for path,owner in [('1/2/1/2','j1'),('1/2/2/5','j2'),('1/2/2/8/6','j2'),('1/2/2/8/9','j3'),('1/2/3/19','j3'),('1/2/3/20','j4'),('1/2/4/14','j4'),('1/2/7/3','j5'),('1/2/7/4','j6'),('1/2/8/6','jaw-right'),('1/2/8/10','jaw-left'),('1/2/3/21/11/1','uwb'),('1/2/5/1','uwb'),('1/2/6/1','camera-lift'),('1/2/8/7','jaw-right'),('1/2/8/9','jaw-left')]:
            self.assertEqual(binding.engineer_group(path),owner)
        self.assertIsNone(binding.engineer_group('1/2/8/1/2/5'))
        self.assertEqual(binding.engineer_group('1/2/8/1/3/5'),'j6')
        self.assertEqual(binding.engineer_group('1/1/63/2'),'j1')
        self.assertEqual(binding.engineer_group('1/1/63/3'),'body')
        self.assertEqual(binding.engineer_group('1/3'),'j2')
        self.assertEqual(binding.engineer_group('1/3/1'),'j2')
        self.assertEqual(binding.engineer_group('1/30'),'body')
    def test_camera_cable_omission_keeps_housing_and_lift_hardware(self):
        for branch in ['4','5']:
            root='1/2/6/1/1/1/1/'+branch
            self.assertIsNone(binding.engineer_group(root))
            for leaf in ['1','2','3','4']:
                self.assertIsNone(binding.engineer_group(root+'/1/1/'+leaf))
        for path in ['1/2/6/1/1/1/1/1','1/2/6/1/1/1/1/40','1/2/6/2','1/2/6/3','1/2/6/10']:
            self.assertEqual(binding.engineer_group(path),'camera-lift')
    def test_all_core_shells_have_exactly_one_owner_and_new_shells_fail(self):
        self.assertEqual({binding.core_arm_group(i) for i in range(1,53)}, {'j1','j2','j3','j4','j5','j6'})
        self.assertEqual({binding.core_head_group(i) for i in range(1,1601)}, {'j6','p','q'})
        self.assertEqual(binding.core_head_group(1224),'q');self.assertEqual(binding.core_head_group(1589),'q')
        self.assertEqual(binding.core_head_group(1223),'q');self.assertEqual(binding.core_head_group(1430),'p')
        for f,index in [(binding.core_arm_group,53),(binding.core_head_group,1601)]:
            with self.assertRaises(ValueError):f(index)

if __name__=='__main__':unittest.main()
