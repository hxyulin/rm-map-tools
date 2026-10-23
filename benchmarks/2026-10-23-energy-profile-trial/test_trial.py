#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Artifact-level invariants for the complete-meridian Energy trial."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_collision_profiles import mesh_metrics
from gltf_scene import accessor,read_glb,scene_nodes
from plan_cad_lods import digest
from simplify_package import scene_triangles
OUT=ROOT/'out/rmuc2027-energy-profile-trial'

class EnergyTrial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((OUT/'results.json').read_bytes())
        cls.baseline,cls.blob=read_glb(cls.report['baseline']['path'])
        cls.mesh=cls.report['baseline']['energy_shared_mesh']

    def payloads(self):
        for row in self.report['trials']:
            yield row,*read_glb(row['output']['path'])

    def test_hashes_and_counts(self):
        for row,d,b in self.payloads():
            self.assertEqual(digest(Path(row['output']['path'])),row['output']['sha256'])
            self.assertEqual(scene_triangles(d),67315-(784-row['triangles'])*12)
            self.assertEqual(row['map_collision_placed_triangles'],196332-row['placed_saving'])

    def test_unchanged_other_arrays_and_scene_metadata(self):
        for row,d,b in self.payloads():
            for key in set(self.baseline)-{'meshes','accessors','bufferViews','buffers'}:
                self.assertEqual(d[key],self.baseline[key],key)
            self.assertEqual(b[:len(self.blob)],self.blob)
            for mi,mesh in enumerate(self.baseline['meshes']):
                if mi==self.mesh: continue
                self.assertEqual(d['meshes'][mi],mesh)
                for pr in mesh['primitives']:
                    for ai in [*pr['attributes'].values(),pr['indices']]:
                        np.testing.assert_array_equal(accessor(d,b,ai),accessor(self.baseline,self.blob,ai))

    def test_exact_complete_meridian_rings(self):
        loops=self.report['source']['meridian_loops']
        expected=np.unique(np.concatenate([r['points_ry_mm'] for r in loops]),axis=0)
        for row,d,b in self.payloads():
            pr=d['meshes'][self.mesh]['primitives'][0]
            p=np.unique(accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000,axis=0)
            ry=np.column_stack([np.linalg.norm(p[:,[0,2]],axis=1),p[:,1]])
            for r,y in expected:
                matches=(abs(ry[:,0]-r)<1e-4)&(abs(ry[:,1]-y)<1e-4)
                self.assertEqual(int(matches.sum()),1 if r<1e-6 else row['angular_segments'])
            self.assertTrue(np.all(np.min(np.linalg.norm(ry[:,None]-expected[None],axis=2),axis=1)<1e-4))

    def test_closed_outward_and_reversed_winding_detected(self):
        for row,d,b in self.payloads():
            pr=d['meshes'][self.mesh]['primitives'][0]
            p=accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000;t=accessor(d,b,pr['indices']).reshape(-1,3)
            p,inv=np.unique(p,axis=0,return_inverse=True);t=inv[t]
            metrics=mesh_metrics(p,t)
            self.assertTrue(metrics['closed_oriented_manifold']);self.assertGreater(metrics['signed_volume_mm3'],0)
            self.assertLess(mesh_metrics(p,t[:,::-1])['signed_volume_mm3'],0)
            broken=t.copy();broken[0]=broken[0,::-1]
            self.assertFalse(mesh_metrics(p,broken)['closed_oriented_manifold'])

    def test_twelve_owners_share_one_blue_definition(self):
        for row,d,b in self.payloads():
            uses=[i for i,_,_ in scene_nodes(d) if d['nodes'][i].get('mesh')==self.mesh]
            self.assertEqual(uses,[x[0] for x in self.report['baseline']['energy_owner_rows']])
            self.assertEqual(len(uses),12)
            self.assertEqual(d['meshes'][self.mesh]['primitives'][0]['material'],2)
            self.assertEqual(d['materials'],self.baseline['materials'])

    def test_policy_and_original_clearance_results(self):
        self.assertEqual([r['angular_segments'] for r in self.report['trials'] if r['passes_original_6mm_guard']],[16])
        for row in self.report['trials']:
            e=row['native_exterior_deviation_mm']
            self.assertEqual(row['passes_original_6mm_guard'],max(e['max'],e['maximum_vertex_distance_mm'])<=6)
            c=row['exported_clearance']
            self.assertEqual(c['socket_stop_rays'],48);self.assertEqual(c['sampled_projectile_centers'],816)
            self.assertLessEqual(c['maximum_socket_stop_shift_mm'],2)
            self.assertGreaterEqual(c['minimum_sampled_socket_surface_clearance_mm'],8.5)
            self.assertEqual(c['socket_recess_occupancy'],[False,False,True,True])
            self.assertTrue(row['output']['render_load_stage_passed'])

if __name__=='__main__':
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EnergyTrial))
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'output':stream.getvalue(),'test_producer_sha256':digest(Path(__file__))}
    (OUT/'tests.json').write_text(json.dumps(report,indent=2)+'\n');print(stream.getvalue())
    tracked=Path(__file__).with_name('results.json');record=json.loads(tracked.read_bytes());record['tests']={'path':str(OUT/'tests.json'),'sha256':digest(OUT/'tests.json'),'passed':result.wasSuccessful(),'count':result.testsRun};tracked.write_text(json.dumps(record,indent=2)+'\n')
    sys.exit(not result.wasSuccessful())
