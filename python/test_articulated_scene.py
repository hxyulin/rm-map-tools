# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import unittest
import numpy as np
from articulated_scene import topology, extract_geometry, link_poses, placement
from export_semantics import apply_pose
from gltf_scene import mesh_instances
from test_gltf_scene import fixture


def rig():
    doc, binary = fixture()
    doc['nodes'][0]['children'] = [2, 3]
    doc['nodes'] += [{'translation': [0, 2, 0], 'rotation': [0, 0, 2**-.5, 2**-.5], 'children': [4]},
                     {'children': [1, 5]}, {'translation': [1, 0, 0], 'children': [6]},
                     {'children': [7]}, {'mesh': 0}]
    binding = {'joints': [
        {'id': 'spin', 'type': 'continuous', 'axis': [1, 0, 0], 'origin_node': 3, 'motion_node': 4},
        {'id': 'slide', 'type': 'prismatic', 'axis': [0, 0, 1], 'limits': [-.2, .4], 'origin_node': 5, 'motion_node': 6}]}
    return doc, binary, binding


class ArticulatedSceneTests(unittest.TestCase):
    def test_serial_transformed_pivots_match_source_pose(self):
        doc, binary, binding = rig()
        graph, _ = topology(doc, binding)
        geometry = extract_geometry(doc, binary, binding, graph)
        self.assertEqual(graph['slide']['parent'], 'spin')
        for q in ({}, {'spin': .7, 'slide': .3}):
            poses = link_poses(graph, q)
            expected = list(mesh_instances(apply_pose(doc, binding['joints'], q), binary))
            for g, (_, _, points, _, _) in zip(geometry, expected):
                m = poses[g['link']]
                np.testing.assert_allclose(g['points'] @ m[:3, :3].T + m[:3, 3], points, atol=1e-12)

    def test_invalid_and_unbound_coordinates(self):
        doc, _, binding = rig()
        graph, _ = topology(doc, binding)
        for q in ({'bad': 1}, {'slide': .5}, {'spin': float('nan')}):
            with self.assertRaises(ValueError):
                link_poses(graph, q)
        graph['spin']['joint']['geometry_binding'] = 'frames_only'
        with self.assertRaises(ValueError):
            link_poses(graph, {'spin': .1})

    def test_collision_mismatch_and_duplicate_rejected(self):
        doc, binary, binding = rig()
        graph, _ = topology(doc, binding)
        bad = copy.deepcopy(binding)
        bad['joints'][0]['axis'] = [0, 1, 0]
        with self.assertRaises(ValueError):
            extract_geometry(doc, binary, bad, graph)
        bad = copy.deepcopy(binding)
        bad['joints'].append(bad['joints'][0])
        with self.assertRaises(ValueError):
            topology(doc, bad)

    def test_placement_forms_and_scale_rejection(self):
        m = placement({'translation_m': [1, 2, 3], 'rotation_xyzw': [0, 0, 1, 0]})
        np.testing.assert_allclose(placement({'matrix_local_to_arena': m.tolist()}), m)
        m[0, 0] = 2
        with self.assertRaises(ValueError):
            placement({'matrix_local_to_arena': m.tolist()})


if __name__ == '__main__':
    unittest.main()
