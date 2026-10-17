# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Affine finite-patch templates preserve bounded geometry and source uses."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from cad_document import CadDocument
from cad_patch_matching import polygon_patch
from cad_patch_instances import affine_patch,TEMPLATES
from test_cad_patch_fits import polygon_records
from test_p21model import FIXTURE
from test_cad_share_values import UNITS
from export_field_package import GlbWriter
from gltf_scene import read_glb,mesh_instances


class PatchInstanceTests(unittest.TestCase):
    def patch(self,tmp,points):
        records,face=polygon_records(100,points)
        path=Path(tmp)/'fixture.step';path.write_text(FIXTURE.replace('ENDSEC;\nEND-ISO-10303-21;',records+UNITS+'ENDSEC;\nEND-ISO-10303-21;'))
        doc=CadDocument.from_step(path)
        return doc,polygon_patch(doc,face)

    def test_different_dimensions_and_source_aliases_share_one_quad(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc,patch=self.patch(tmp,[[10,20,0],[14,20,0],[14,22,0],[10,22,0]])
            with doc:
                use=affine_patch(patch,component_id='part-a',source_colour='1,0,0',collision_role='marking')
                self.assertEqual(use.template,'quad')
                np.testing.assert_allclose(use.positions_mm(),patch.coordinates())
                self.assertEqual(use.source_edge_ids,patch.edge_ids)
                self.assertEqual(use.component_id,'part-a');self.assertEqual(use.collision_role,'marking')
                self.assertGreater(np.linalg.det(use.matrix_m()[:3,:3]),0)
                self.assertLessEqual(use.boundary_error_bound_mm,1e-6)

    def test_collinear_export_subdivisions_reduce_without_losing_source_ids(self):
        points=[[0,0,0],[1,0,0],[2,0,0],[4,0,0],[4,2,0],[0,2,0]]
        with tempfile.TemporaryDirectory() as tmp:
            doc,patch=self.patch(tmp,points)
            with doc:
                use=affine_patch(patch,component_id='part')
                self.assertEqual(len(use.source_vertex_ids),6)
                self.assertEqual(len(use.retained_corner_indices),4)
                self.assertEqual(len(TEMPLATES[use.template][1]),2)
                self.assertLessEqual(use.boundary_error_bound_mm,1e-6)

    def test_trapezoid_over_budget_and_self_intersection_are_rejected(self):
        for points in ([[0,0,0],[4,0,0],[4,2.001,0],[0,2,0]],
                       [[0,0,0],[4,0,0],[5,2,0],[1,2,0]],
                       [[0,0,0],[4,2,0],[0,3,0],[4,0,0]]):
            with tempfile.TemporaryDirectory() as tmp:
                doc,patch=self.patch(tmp,points)
                with doc,self.assertRaises(ValueError):affine_patch(patch,component_id='part')

    def test_triangle_and_reversed_source_facing_keep_winding(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            doc,patch=self.patch(tmp,[[0,0,0],[5,0,0],[1,3,0]])
            with doc:
                use=affine_patch(patch,component_id='triangle')
                reverse=affine_patch(replace(patch,orientations=(False,)+patch.orientations[1:]),component_id='reverse')
                self.assertEqual(use.template,'triangle')
                a,b=use.positions_mm(),reverse.positions_mm()
                self.assertGreater(np.cross(a[1]-a[0],a[2]-a[0])[2],0)
                self.assertLess(np.cross(b[1]-b[0],b[2]-b[0])[2],0)

    def test_material_variants_share_payload_and_keep_instance_metadata(self):
        p,t=TEMPLATES['quad'];n=np.tile([0.,0,1],(4,1));writer=GlbWriter('root',{'version':'2.0'})
        for i,color in enumerate(['1,0,0','0,0,1','1,0,0']):
            matrix=np.eye(4);matrix[0,0]=i+1;matrix[0,3]=i*10
            writer.add_indexed_instance(str(i),p,n,t,color,matrix=matrix,extras={'owner':i})
        self.assertEqual(len(writer.meshes),2)
        a,b=[m['primitives'][0] for m in writer.meshes]
        self.assertEqual(a['attributes'],b['attributes']);self.assertEqual(a['indices'],b['indices'])
        self.assertEqual(len(writer.bin),108)
        self.assertEqual(len(writer.nodes),3)
        self.assertNotEqual(writer.nodes[0]['extras'],writer.nodes[2]['extras'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'instances.glb';writer.write(path);d,binary=read_glb(path)
            decoded=list(mesh_instances(d,binary))
            self.assertEqual(len(decoded),3)
            self.assertAlmostEqual(decoded[2][2][:,0].max(),23)
        writer.add_indexed_instance('different-normal',p,-n,t,'1,0,0',matrix=np.eye(4))
        self.assertEqual(len(writer._indexed_payloads),2)

    def test_layer_keeps_every_unsupported_face_and_validates_source_context(self):
        from cad_patch_instances import build_patch_instances
        a,fa=polygon_records(100,[[0,0,0],[4,0,0],[4,2,0],[0,2,0]])
        b,fb=polygon_records(200,[[0,0,0],[4,0,0],[4,2.01,0],[0,2,0]])
        text=FIXTURE.replace("#8=ADVANCED_FACE('',(),$,.T.);\n",'')
        text=text.replace("#7=OPEN_SHELL('',(#8));",f"#7=OPEN_SHELL('',(#{fa},#{fb}));")
        text=text.replace('ENDSEC;\nEND-ISO-10303-21;',a+b+UNITS+'ENDSEC;\nEND-ISO-10303-21;')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'layer.step';path.write_text(text)
            with CadDocument.from_step(path) as doc:
                hierarchy={'files_sha256':{'field.step':doc.source_sha256},'source_face_definitions':2,
                           'components':[{'id':'part','face_ids':[fa,fb],'export_body_ids':{'6':6}}]}
                layer=build_patch_instances(doc,hierarchy)
                self.assertEqual([u.source_face_id for u in layer.uses],[fa])
                self.assertEqual(layer.fallback_face_ids,(fb,))
                self.assertEqual(layer.statistics()['source_faces'],2)
                with self.assertRaises(ValueError):build_patch_instances(doc,hierarchy,budget_mm=-1)
                hierarchy['files_sha256']['field.step']='0'*64
                with self.assertRaisesRegex(ValueError,'source mismatch'):build_patch_instances(doc,hierarchy)

    def test_compact_layer_roundtrip_keeps_all_roles_aliases_and_fallbacks(self):
        from dataclasses import replace
        from cad_patch_instances import PatchInstanceLayer
        from cad_patch_storage import write_layer,read_layer
        with tempfile.TemporaryDirectory() as tmp:
            doc,patch=self.patch(tmp,[[0,0,0],[4,0,0],[4,2,0],[0,2,0]])
            with doc:
                a=affine_patch(patch,component_id='red',source_colour='1,0,0',appearance_target_id=123,collision_role='marking')
                b=replace(a,source_face_id=a.source_face_id+1000,component_id='blue',source_colour=None,
                          appearance_target_id=None,collision_role='structural')
                layer=PatchInstanceLayer(doc.source_sha256,1e-6,(a,b),(9999,),(('unsupported',1),),3)
                path=Path(tmp)/'layer';stats=write_layer(layer,path)
                self.assertTrue(stats['all_use_fields_preserved'])
                self.assertEqual(read_layer(path,expected_source_sha256=doc.source_sha256),layer)
                pooled=Path(tmp)/'pooled';pooled_stats=write_layer(layer,pooled,frame_encoding='auto')
                self.assertEqual(pooled_stats['frame_encoding'],'exact-edge-vector-pool')
                self.assertEqual(read_layer(pooled,expected_source_sha256=doc.source_sha256),layer)
                with self.assertRaises(FileExistsError):write_layer(layer,path)
                with self.assertRaisesRegex(ValueError,'source mismatch'):read_layer(path,expected_source_sha256='0'*64)
                payload=bytearray((path/'instances.npz').read_bytes());payload[-1]^=1
                (path/'instances.npz').write_bytes(payload)
                with self.assertRaisesRegex(ValueError,'checksum'):read_layer(path,expected_source_sha256=doc.source_sha256)

    def test_invalid_normal_or_singular_transform_is_rejected(self):
        p,t=TEMPLATES['triangle'];n=np.tile([0.,0,1],(3,1));writer=GlbWriter('root',{'version':'2.0'})
        with self.assertRaises(ValueError):writer.add_indexed_instance('bad',p,n*0,t,None,matrix=np.eye(4))
        with self.assertRaises(ValueError):writer.add_indexed_instance('bad',p,n,t,None,matrix=np.zeros((4,4)))
        shear=np.eye(4);shear[0,1]=.5
        with self.assertRaisesRegex(ValueError,'shear'):writer.add_indexed_instance('bad',p,n,t,None,matrix=shear)


if __name__=='__main__':unittest.main()
