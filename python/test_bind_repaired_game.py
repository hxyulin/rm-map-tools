# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Rest frames and source detector envelopes survive structured joint export."""
import copy
import unittest
import numpy as np
from bind_repaired_game import reparent_joint, fit_detector
from gltf_scene import scene_nodes, local_matrix


class RepairedBindingTests(unittest.TestCase):
    def test_joint_changes_only_its_subtree_and_rotates_about_exported_pivot(self):
        d = {'scenes': [{'nodes': [0]}], 'nodes': [
            {'translation': [3., 1., 2.], 'children': [1, 2]},
            {'translation': [1., 2., 0.], 'children': [3]},
            {'translation': [-2., 0., 0.]}, {'translation': [0., 0., 1.]}]}
        old = {i: w for i, w, parent in scene_nodes(d)}
        pivot = np.array([4., 5., 6.])
        reparent_joint(d, [1], 'outpost.spin', pivot, [0., 1., 0.], None)
        current = {i: w for i, w, parent in scene_nodes(d)}
        for i in old: np.testing.assert_allclose(current[i], old[i], atol=1e-12)
        joint = next(n for n in d['nodes'] if n.get('name') == 'outpost.spin')
        joint['rotation'] = [0., np.sin(.25), 0., np.cos(.25)]
        current = {i: w for i, w, parent in scene_nodes(d)}
        rotation = local_matrix({'rotation': joint['rotation']})
        origin = np.eye(4); origin[:3, 3] = pivot
        np.testing.assert_allclose(current[3], origin @ rotation @ np.linalg.inv(origin) @ old[3], atol=1e-12)
        np.testing.assert_allclose(current[2], old[2], atol=1e-12)

    def test_joint_refuses_unrelated_parents_without_modifying_input(self):
        d = {'scenes': [{'nodes': [0]}], 'nodes': [{'children': [1, 2]}, {'children': [3]}, {}, {}]}
        before = copy.deepcopy(d)
        with self.assertRaises(ValueError): reparent_joint(d, [2, 3], 'bad', np.zeros(3), [0, 1, 0], None)
        self.assertEqual(d, before)

    def test_source_optics_supply_orientation_and_source_module_supplies_envelope(self):
        p = np.array([[-.045, -.04, .01], [.045, -.04, .01], [.045, .04, .01], [-.045, .04, .01]])
        t = np.array([[0, 1, 2], [0, 2, 3]])
        center, basis, half = fit_detector(p, t, np.ones(2, bool))
        np.testing.assert_allclose(half, [.045, .04])
        np.testing.assert_allclose(center, [0, 0, .0115])
        np.testing.assert_allclose(basis[:, 0], [0, 0, 1])

    def test_detector_rejects_missing_optics(self):
        p = np.array([[0., 0, .01], [.01, 0, .01], [0, .01, .01]])
        with self.assertRaises(ValueError): fit_detector(p, np.array([[0, 1, 2]]), np.array([False]))


if __name__ == '__main__': unittest.main()
