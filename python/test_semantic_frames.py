# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import unittest

import numpy as np

from export_semantics import apply_pose, transform_asset
from gltf_scene import scene_nodes
from test_gltf_scene import fixture


def serial_rules():
    return {
        'id': 'arm',
        'nodes': [{'select': {'name': 'root'},
                   'metadata': {'id': 'root', 'roles': ['assembly']}}],
        'frames': [
            {'parent': 'root', 'translation_m': [1, 0, 0],
             'metadata': {'id': 'a', 'roles': ['arm']}, 'evidence': ['fixture']},
            {'parent': 'a', 'translation_m': [1, 0, 0],
             'metadata': {'id': 'b', 'roles': ['arm']}, 'evidence': ['fixture']}],
        'joints': [
            {'id': 'shoulder', 'type': 'revolute', 'parent': 'root', 'children': ['a'],
             'axis': [0, 0, 1], 'origin_m': [0, 0, 0], 'evidence': ['fixture'],
             'preview_range': [-.1, .1]},
            {'id': 'elbow', 'type': 'revolute', 'parent': 'a', 'children': ['b'],
             'axis': [0, 0, 1], 'origin_m': [0, 0, 0], 'evidence': ['fixture']}],
    }


class SemanticFrameTests(unittest.TestCase):
    def test_serial_frames_follow_upstream_motion_without_moving_unbound_meshes(self):
        source, _ = fixture()
        doc, meta = transform_asset(source, serial_rules(), 'hash')
        ids = {n['id']: n['node'] for n in meta['nodes']}
        rest = {i: w for i, w, _ in scene_nodes(doc)}
        np.testing.assert_allclose(rest[ids['a']][:3, 3], [11, 0, 0])
        np.testing.assert_allclose(rest[ids['b']][:3, 3], [12, 0, 0])
        # A preview range is not a mechanical limit.
        moved = apply_pose(doc, meta['joints'], {'shoulder': np.pi/2, 'elbow': np.pi/2})
        world = {i: w for i, w, _ in scene_nodes(moved)}
        np.testing.assert_allclose(world[ids['a']][:3, 3], [10, 1, 0], atol=1e-12)
        np.testing.assert_allclose(world[ids['b']][:3, 3], [9, 1, 0], atol=1e-12)
        for i in [0, 1, 2]:
            np.testing.assert_allclose(world[i], rest[i], atol=1e-12)
        self.assertEqual(len(source['nodes']), 3)

    def test_frame_rejects_duplicate_or_forward_parent_and_bad_preview(self):
        doc, _ = fixture()
        for change in ['duplicate', 'parent', 'preview']:
            spec = copy.deepcopy(serial_rules())
            if change == 'duplicate':
                spec['frames'][0]['metadata']['id'] = 'root'
            elif change == 'parent':
                spec['frames'][0]['parent'] = 'b'
            else:
                spec['joints'][0]['preview_range'] = [1, -1]
            with self.assertRaises(ValueError):
                transform_asset(doc, spec, 'hash')
