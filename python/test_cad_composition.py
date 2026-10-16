# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Occurrence selection must preserve shared definitions without extra copies."""
import unittest
from pathlib import Path
import tempfile
import numpy as np
from cad_composition import compile_compositions, product_occurrences, export_composition, verify_composition, validate_footing


def fixture():
    def occurrence(body, path, ancestors):
        return {'component_id': body, 'root_product_id': 1, 'occurrence_path': path,
                'ancestor_product_ids': ancestors, 'source_world_matrix': [[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}
    return {'source_sha256': 'test', 'assemblies': [{'name':'housing','product_id':2}],
            'components': [{'id':'a','product_id':3}, {'id':'b','product_id':3}],
            'occurrences': [occurrence('a',[10,11],[1,2,3]), occurrence('b',[10,11],[1,2,3]),
                            occurrence('a',[20],[1,3]), occurrence('b',[20],[1,3])]}


class CompositionTests(unittest.TestCase):
    def test_footing_pairing_uses_spatial_alignment_not_sibling_order(self):
        footing = (2,np.array([0.,0.,0.]),np.array([1.,1.,.2]))
        tower = (3,np.array([.1,.1,.18]),np.array([.9,.9,2.]))
        validate_footing([footing,tower],2)
        with self.assertRaisesRegex(ValueError,'does not meet'):
            validate_footing([footing,(3,tower[1]+[5,0,0],tower[2]+[5,0,0])],2)

    def test_native_roundtrip_two_instances_rotation_units_and_checksum(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
        from cad_document import CadDocument
        from export_field_package import GlbWriter
        from gltf_scene import read_glb
        from mesh_parts import tessellate
        from p21split import Splitter
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'box.step'
            writer = STEPControl_Writer()
            writer.Transfer(BRepPrimAPI_MakeBox(10,20,30).Shape(), STEPControl_AsIs)
            writer.Write(str(source))
            with CadDocument.from_step(source, workers=1) as document:
                points, triangles, indices, colors = tessellate(document.working_model().document, .4,.25)
                glb = GlbWriter('box', {'version':'2.0'})
                glb.add_node('box',points/1000,triangles,[colors[int(i)] for i in indices])
                glb.write(root/'box.glb')
                product = int(document.index.ids[next(iter(document.model.product_name))])
                first = np.eye(4); first[:3,3]=[1000,2000,3000]
                second = first.copy(); second[:3,:3]=[[0,-1,0],[1,0,0],[0,0,1]]; second[0,3]+=200
                recipe = {'name':'boxes','evidence':'fixture','occurrences':[
                    {'product_id':product,'source_world_matrix':m.tolist(),'occurrence_path':[i]}
                    for i,m in enumerate([first,second])]}
                report = export_composition(document,recipe,{product:{'glb':root/'box.glb','native_faces':6}},
                                            root/'complete',Splitter(document.index,document.model))
                self.assertEqual(report['native_faces'],12)
                self.assertLess(verify_composition(root/'complete',document.source_sha256),1e-6)
                scene,_ = read_glb(root/'complete/visual.glb')
                self.assertEqual(len(scene['meshes']),1)
                self.assertEqual(len([n for n in scene['nodes'] if 'mesh' in n]),2)
                with (root/'complete/visual.glb').open('ab') as stream: stream.write(b'corrupt')
                with self.assertRaisesRegex(ValueError,'checksum'):
                    verify_composition(root/'complete',document.source_sha256)
                document.verify_source()

    def test_product_occurrences_collapse_bodies_but_keep_instances(self):
        self.assertEqual(len(product_occurrences(fixture())), 2)

    def test_subtree_does_not_include_shared_product_elsewhere(self):
        result = compile_compositions(fixture(), {'schema_version':1,'source_sha256':'test',
            'compositions':[{'name':'complete','subtree':'housing','evidence':'original parent'}]})
        self.assertEqual([o['occurrence_path'] for o in result[0]['occurrences']], [[10,11]])

    def test_explicit_paths_reject_missing_duplicate_and_ambiguous(self):
        for paths in [[[99]], [[20],[20]]]:
            with self.assertRaises(ValueError):
                compile_compositions(fixture(), {'schema_version':1,'source_sha256':'test',
                    'compositions':[{'name':'complete','occurrence_paths':paths,'evidence':'reviewed'}]})
        catalog=fixture(); catalog['occurrences'][1]['source_world_matrix'][0][3]=5
        with self.assertRaises(ValueError): product_occurrences(catalog)


if __name__=='__main__': unittest.main()
