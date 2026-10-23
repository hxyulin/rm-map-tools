# SPDX-License-Identifier: MIT OR Apache-2.0
"""Regression: crucial top geometry must survive every remaining review variant."""
import json
import unittest
import numpy as np
from audit import OUT
from trial import digest
from gltf_scene import read_glb,accessor,scene_nodes
from pathlib import Path

class RestorationTests(unittest.TestCase):
    def test_restored_variants_are_byte_exact(self):
        for r in json.loads((OUT/'ledger.json').read_text())['trials']:
            if r['policy']=='vents':
                self.assertEqual(digest(Path(r['source'])),digest(Path(r['output'])))
                self.assertEqual(r['placed_saved_triangles'],0)

    def test_only_independent_arm_housings_can_change(self):
        for r in json.loads((OUT/'ledger.json').read_text())['trials']:
            sd,sb=read_glb(r['source']);d,b=read_glb(r['output'])
            self.assertTrue(all(s['node']==1672 for s in r['selections']))
            for i,w,parent in scene_nodes(sd):
                n=sd['nodes'][i]
                if i==1672 or 'mesh'not in n:continue
                before=sd['meshes'][n['mesh']]['primitives'];after=d['meshes'][d['nodes'][i]['mesh']]['primitives']
                self.assertEqual(len(before),len(after))
                for x,y in zip(before,after):
                    self.assertEqual(x.get('material'),y.get('material'))
                    self.assertEqual(x['attributes'].keys(),y['attributes'].keys())
                    for name,ai in x['attributes'].items():
                        np.testing.assert_array_equal(accessor(sd,sb,ai),accessor(d,b,y['attributes'][name]))
                    np.testing.assert_array_equal(accessor(sd,sb,x['indices']),accessor(d,b,y['indices']))

if __name__=='__main__':unittest.main()
