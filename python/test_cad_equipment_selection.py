# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Triangle omission preserves shared, mirrored and indexed source payloads."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from gltf_scene import read_glb,write_glb,mesh_instances,accessor
from simplify_package import append_accessor
from export_field_package import GlbWriter
from test_cad_collision_proxy import cube
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('equipment_shell_common',ROOT/'benchmarks/2026-10-17-equipment-shells/common.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


def triangles(path):
    d,b=read_glb(path)
    return np.concatenate([p[t]for _,_,p,t,_ in mesh_instances(d,b)])


class EquipmentSelectionTests(unittest.TestCase):
    def test_replacement_keeps_original_member_traversal_priority(self):
        with tempfile.TemporaryDirectory()as directory:
            folder=Path(directory);source=folder/'source.glb';target=folder/'target.glb';p,t=cube();writer=GlbWriter('test',{'version':'2.0'});writer.add_node('first',p/1000,t,['0.2,0.2,0.2']*12,extras={'native_shell_index':1});writer.add_node('second',p/1000,t,['1.0,0.0,0.0']*12,extras={'native_shell_index':2});writer.write(source)
            helper.replace_members(source,target,[(p,t,np.zeros(12,int),1)],['0.2,0.2,0.2','1.0,0.0,0.0'],folder)
            np.testing.assert_array_equal(helper.read_mesh(source)['unit_ids'],helper.read_mesh(target)['unit_ids'])

    def test_partial_mirrored_shared_mesh_does_not_change_other_occurrence(self):
        with tempfile.TemporaryDirectory()as directory:
            folder=Path(directory);source=folder/'source.glb';target=folder/'target.glb';p,t=cube();writer=GlbWriter('test',{'version':'2.0'});writer.add_node('a',p/1000,t,['0.2,0.2,0.2']*len(t),extras={'native_shell_index':1});pose=np.diag([-1.,1,1,1]);pose[0,3]=1;writer.add_node('b',p/1000,t,['0.2,0.2,0.2']*len(t),matrix=pose,extras={'native_shell_index':2});writer.write(source)
            before=triangles(source);keep=np.r_[np.arange(12),np.arange(18,24)];helper.retain_triangles(source,target,keep)
            np.testing.assert_array_equal(triangles(target),before[keep]);d,b=read_glb(target);self.assertEqual(len(d['meshes']),2)

    def test_unused_leading_vertex_does_not_shift_selected_attributes(self):
        with tempfile.TemporaryDirectory()as directory:
            folder=Path(directory);source=folder/'source.glb';target=folder/'target.glb';p,t=cube();writer=GlbWriter('test',{'version':'2.0'});writer.add_node('a',p/1000,t,['0.2,0.2,0.2']*len(t),extras={'native_shell_index':1});writer.write(source);d,b=read_glb(source);binary=bytearray(b);prim=d['meshes'][0]['primitives'][0]
            for key,index in list(prim['attributes'].items()):
                values=accessor(d,b,index);values=np.concatenate([np.full_like(values[:1],123),values]);prim['attributes'][key]=append_accessor(d,binary,values,'VEC3',5126)
            indices=accessor(d,b,prim['indices']).astype(np.uint32)+1;prim['indices']=append_accessor(d,binary,indices,'SCALAR',5125);write_glb(source,d,binary);before=triangles(source);helper.retain_triangles(source,target,np.arange(6));np.testing.assert_array_equal(triangles(target),before[:6])


if __name__=='__main__':unittest.main()
