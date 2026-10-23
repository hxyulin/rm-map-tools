# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reviewed source ownership must fail closed and survive STEP hierarchy export."""
import copy
from pathlib import Path
import tempfile
import unittest
from cad_motion import compile_source_motion
from cad_partition import compile_partition
from test_cad_partition import PartitionTests


class SourceMotionTests(unittest.TestCase):
    def policy(self,doc):
        return {'schema_version':1,'source_sha256':doc.source_sha256,
                'joints':[{'id':'part.slide','source_product_id':1}],
                'selections':[{'product_id':1,'group':'part/moving','motion_owner':'part.slide',
                               'units':[{'body_id':6,'face_ids':[8]}],'evidence':['reviewed fixture']}],
                'product_defaults':{'1':'part/fixed'}}

    def test_partition_resolves_mixed_solid_into_disjoint_original_faces(self):
        helper=PartitionTests()
        with helper.document(solid=True) as doc:
            motion=compile_source_motion(doc,self.policy(doc))
            p=helper.policy(doc);p['products'][0]['shell_rules']=[]
            result=compile_partition(doc,helper.catalog(doc),p,source_motion=motion)['products'][0]
            groups={g['id']:g for g in result['groups']}
            self.assertEqual(groups['part/moving']['face_ids_by_body'],{'6':[8]})
            self.assertEqual(groups['part/fixed']['face_ids_by_body'],{'6':[28]})
            self.assertEqual(groups['part/moving']['solid_body_ids'],[])
            self.assertEqual(groups['part/moving']['motion_owners'],['part.slide'])
            self.assertEqual(set(groups['part/moving']['face_ids']) & set(groups['part/fixed']['face_ids']),set())

    def test_rejects_tampering_overlap_foreign_units_and_wrong_joint_owner(self):
        helper=PartitionTests()
        with helper.document(solid=True) as doc:
            policy=self.policy(doc)
            changed=copy.deepcopy(policy);changed['source_sha256']='wrong'
            with self.assertRaisesRegex(ValueError,'SHA'):compile_source_motion(doc,changed)
            changed=copy.deepcopy(policy);changed['selections'].append({**changed['selections'][0],'group':'part/duplicate'})
            with self.assertRaisesRegex(ValueError,'multiple motion'):compile_source_motion(doc,changed)
            changed=copy.deepcopy(policy);changed['selections'][0]['units']=[{'body_id':999}]
            with self.assertRaisesRegex(ValueError,'outside'):compile_source_motion(doc,changed)
            changed=copy.deepcopy(policy);changed['joints'][0]['source_product_id']=99
            with self.assertRaisesRegex(ValueError,'motion owner'):compile_source_motion(doc,changed)
            changed=copy.deepcopy(policy);changed['selections'][0]['units']=[{'body_id':6,'face_ids':[8,8]}]
            with self.assertRaisesRegex(ValueError,'duplicate'):compile_source_motion(doc,changed)

    def test_native_hierarchy_preserves_faces_appearance_and_shared_occurrence(self):
        from test_cad_hierarchy import shell_fixture
        from cad_document import CadDocument
        from cad_components import build_catalog
        from cad_hierarchy import write_hierarchy,native_validate
        from validate_parts import read_part
        from mesh_parts import tessellate
        from collections import Counter
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);path=root/'source.step';shell_fixture(path)
            with CadDocument.from_step(path,workers=1) as doc:
                ix,m=doc.index,doc.model;body=m.bodies[0][0];bid=int(ix.ids[body]);pid=int(ix.ids[m.rep_product[m.bodies[0][1]]]);face=int(ix.ids[m.body_faces(body)[0]])
                policy={'schema_version':1,'source_sha256':doc.source_sha256,'product_names':{str(pid):'fixture'},'groups':[]}
                catalog=build_catalog(doc,policy,{'schema_version':1,'source_sha256':doc.source_sha256,'assignments':[]})
                catalog['occurrences'].append({**catalog['occurrences'][0],'occurrence_path':[999]})
                motion=compile_source_motion(doc,{'schema_version':1,'source_sha256':doc.source_sha256,'joints':[],
                    'selections':[{'product_id':pid,'group':'fixture/moving','units':[{'body_id':bid,'face_ids':[face]}],'evidence':['native face split']}],
                    'product_defaults':{str(pid):'fixture/fixed'}})
                partition=compile_partition(doc,catalog,{'schema_version':1,'source_sha256':doc.source_sha256,'length_unit':'millimetre','products':[{'product_id':pid,'name':'fixture','fallback_group':'fixture/source'}]},source_motion=motion)
                report=write_hierarchy(doc,catalog,[partition],[],{'name':'field','secondary_product_ids':[],'equipment_product_ids':[]},root/'export')
                self.assertEqual(report['face_patch_body_ids'],[bid]);self.assertEqual(report['source_face_definitions'],12)
                native=native_validate(root/'export');self.assertEqual(native['native_faces'],24)
                def colors(p):
                    d,_,err=read_part(str(p));self.assertIsNone(err)
                    _,_,ids,keys=tessellate(d,.4,.25);return Counter(keys[int(i)]for i in ids)
                original=colors(path);self.assertNotIn(None,original)
                self.assertEqual(colors(root/'export/field.step'),Counter({c:n*2 for c,n in original.items()}))

if __name__=='__main__':unittest.main()
