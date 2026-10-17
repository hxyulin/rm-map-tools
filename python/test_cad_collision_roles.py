# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Visual-only markings retain ownership and continuous collision backing."""
from copy import deepcopy
import unittest
from cad_collision_roles import CollisionRoles


def fixture():
    hierarchy={'files_sha256':{'field.step':'a'*64},'components':[
        {'id':'border','face_ids':[1,2]}, {'id':'floor','face_ids':[3,4]}, {'id':'unknown','face_ids':[5]}]}
    data={'schema_version':1,'source_sha256':'a'*64,'hierarchy_sha256':'b'*64,'entries':[
        {'component_id':'border','role':'marking','visual':True,'collision':False,
         'selection':'component','source_face_ids':[1,2],'backing_required':False},
        {'component_id':'floor','role':'marking','visual':True,'collision':False,
         'selection':'faces','source_face_ids':[4],'backing_required':True}]}
    return data,hierarchy


class CollisionRoleTests(unittest.TestCase):
    def policy(self):
        data,hierarchy=fixture()
        return CollisionRoles(data,hierarchy,hierarchy_sha256='b'*64)

    def test_border_has_zero_collision_but_all_visual_faces(self):
        p=self.policy();self.assertFalse(p.collision_enabled('border'))
        result=p.partition('border',[1,1,2])
        self.assertEqual(result['collision'],[])
        self.assertEqual(result['visual_only_marking'],[0,1,2])
        self.assertEqual(result['unpainted_backing'],[])

    def test_embedded_paint_keeps_backing_without_becoming_collision_artwork(self):
        p=self.policy();result=p.partition('floor',[3,4,4])
        self.assertTrue(p.collision_enabled('floor'))
        self.assertEqual(result['structural'],[0])
        self.assertEqual(result['visual_only_marking'],[1,2])
        self.assertEqual(result['unpainted_backing'],[1,2])
        self.assertEqual(result['collision'],[0,1,2])
        self.assertEqual(p.partition('unknown',[5])['structural'],[0])

    def test_policies_pin_source_ownership_and_cannot_drop_backing(self):
        for field,value in [('source_sha256','c'*64),('hierarchy_sha256','c'*64)]:
            data,hierarchy=fixture();data[field]=value
            with self.assertRaises(ValueError):CollisionRoles(data,hierarchy,hierarchy_sha256='b'*64)
        for change in [{'source_face_ids':[99]},{'source_face_ids':[1]}, {'collision':True}]:
            data,hierarchy=fixture();data['entries'][0].update(change)
            with self.assertRaises(ValueError):CollisionRoles(data,hierarchy,hierarchy_sha256='b'*64)
        data,hierarchy=fixture();data['entries'][1]['backing_required']=False
        with self.assertRaises(ValueError):CollisionRoles(data,hierarchy,hierarchy_sha256='b'*64)
        with self.assertRaises(ValueError):self.policy().partition('floor',[1])

    def test_role_reads_do_not_mutate_shared_policy(self):
        p=self.policy();binding=p.binding('border');binding['collision']=True
        self.assertFalse(p.binding('border')['collision'])


if __name__=='__main__':unittest.main()
