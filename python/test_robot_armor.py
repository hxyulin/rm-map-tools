# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source armor identification keeps carriers and rejects incomplete modules."""
import copy
import unittest

import numpy as np

from robot_armor import identify_armor, strip_armor_surfaces, verify_armor_replacement, merge_armor_aliases


class ArmorBindingTests(unittest.TestCase):
    def fixture(self):
        d = {'scene': 0, 'scenes': [{'nodes': list(range(5))}], 'nodes': [], 'meshes': [],
             'materials': [{}], 'buffers': [{}], 'bufferViews': [], 'accessors': []}
        b = bytearray()
        normal = np.array([0., np.sin(np.pi/12), np.cos(np.pi/12)])
        up = np.array([0.,np.cos(np.pi/12),-np.sin(np.pi/12)])
        basis = np.column_stack([normal, np.cross(up,normal), up])
        for i, (center, size) in enumerate([
            ([0,0,0], [.003,.130,.135]), ([-.008,0,0], [.013,.141,.135]),
            ([0,-.065,0], [.014,.018,.059]), ([0,.065,0], [.014,.018,.059]),
            ([-.025,0,0], [.003,.034,.045])]):
            p = np.array([[x,y,z] for x in [-.5,.5] for y in [-.5,.5] for z in [-.5,.5]]) * size + center
            p = (p @ basis.T + [0,.2,.3]).astype('<f4')
            t = np.array([0,1,3,0,3,2,4,6,7,4,7,5,0,4,5,0,5,1,2,3,7,2,7,6,0,2,6,0,6,4,1,5,7,1,7,3],dtype='<u4')
            attrs = []
            for values, typ, component in [(p,'VEC3',5126),(t,'SCALAR',5125)]:
                view = len(d['bufferViews']);d['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':values.nbytes})
                attrs.append(len(d['accessors']));d['accessors'].append({'bufferView':view,'componentType':component,'count':len(values),'type':typ});b.extend(values.tobytes())
            d['meshes'].append({'primitives':[{'attributes':{'POSITION':attrs[0]},'indices':attrs[1],'material':0}]})
            d['nodes'].append({'mesh':i,'extras':{'source_occurrence_paths':['1/1'],'native_solid_index':i+1}})
        d['buffers'][0]['byteLength'] = len(b)
        return d, bytes(b), [{'path':'1/1','name':'RM2019裁判系统装甲模块AM02'}]

    def test_module_fit_replaces_four_surfaces_and_keeps_mounting_hardware(self):
        d,b,rows = self.fixture();original = copy.deepcopy(d)
        r = identify_armor(d,b,rows)
        self.assertEqual(len(r['modules']),1)
        m = r['modules'][0]
        self.assertEqual(m['kind'],'AM02')
        self.assertEqual([p['node'] for p in m['replace_surfaces']], [0,1,2,3])
        matrix = np.array(m['face_matrix_gltf']).reshape(4,4,order='F')
        self.assertGreater(np.linalg.det(matrix[:3,:3]),.99999)
        self.assertGreater(matrix[1,0], .25)
        strip_armor_surfaces(d,r)
        self.assertEqual(d['nodes'][4],original['nodes'][4])
        self.assertTrue(verify_armor_replacement(original,d,r)['only_selected_surfaces_removed'])
        d['nodes'][4].pop('mesh')
        with self.assertRaises(AssertionError):verify_armor_replacement(original,d,r)

    def test_unrecognized_leaf_is_not_guessed_from_shape(self):
        d,b,rows = self.fixture();rows[0]['name']='ordinary machined plate'
        self.assertEqual(identify_armor(d,b,rows)['modules'],[])

    def test_incomplete_module_fails_closed(self):
        d,b,rows = self.fixture();d['scenes'][0]['nodes'].remove(3)
        with self.assertRaisesRegex(ValueError,'two diffusers'):identify_armor(d,b,rows)

    def test_aliases_require_explicit_paths_and_close_poses(self):
        d,b,rows=self.fixture();r=identify_armor(d,b,rows)
        alias=copy.deepcopy(r['modules'][0]);alias['source_paths']=['1/2'];alias['face_matrix_gltf'][13]+=.001
        r['modules'].append(alias)
        bad=copy.deepcopy(r);bad['modules'][1]['face_matrix_gltf'][13]+=.01
        with self.assertRaisesRegex(ValueError,'no longer coincides'):
            merge_armor_aliases(bad,[{'primary':'1/1','alias':'1/2'}])
        merge_armor_aliases(r,[{'primary':'1/1','alias':'1/2'}])
        self.assertEqual(len(r['modules']),1)
        self.assertEqual(len(r['modules'][0]['replace_surfaces']),8)


if __name__ == '__main__':unittest.main()
