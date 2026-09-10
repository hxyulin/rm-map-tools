# SPDX-License-Identifier: MIT OR Apache-2.0
import json
from pathlib import Path
import unittest

import numpy as np

from export_semantics import apply_pose, transform_asset
from gltf_scene import scene_nodes
from preview.tech_core_demo import forward, solve_translation, solve_poses, sequence_targets
from test_gltf_scene import fixture


class TechCoreDemoTests(unittest.TestCase):
    def test_ik_translates_tool_without_changing_orientation(self):
        rules = json.loads((Path(__file__).resolve().parent.parent/'rules/semantics-legacy-equipment.json').read_text())
        spec = rules['assets']['tech-core']
        axes = [(np.asarray(j['origin_m']), np.asarray(j['axis'])) for j in spec['joints']]
        point = np.array([-.3, .25, .3])
        direction = np.array([1., -1., 0])/np.sqrt(2)
        distances = [0, .05, .1, 0]
        values, report = solve_translation(axes, point, direction, distances)
        for distance, q in zip(distances, values):
            pose = forward(axes, q)
            np.testing.assert_allclose(pose[:3, :3], np.eye(3), atol=1e-8)
            np.testing.assert_allclose(pose[:3, :3] @ point + pose[:3, 3],
                                       point + direction*distance, atol=1e-8)
        self.assertLess(report['maximum_position_error_m'], 1e-8)

    def test_pose_tour_closes_and_retains_exact_insertion(self):
        rules = json.loads((Path(__file__).resolve().parent.parent/'rules/semantics-legacy-equipment.json').read_text())
        axes = [(np.asarray(j['origin_m']), np.asarray(j['axis'])) for j in rules['assets']['tech-core']['joints']]
        point = np.array([-.333812, .268326, .257028])
        direction = np.array([1., -1., 0])/np.sqrt(2)
        phases = np.linspace(0, 1, 71)
        targets, rotations = sequence_targets(point, direction, phases)
        values, report = solve_poses(axes, point, targets, rotations)
        np.testing.assert_allclose(targets[[0, -1]], [point, point], atol=1e-12)
        np.testing.assert_allclose(values[-1], values[0], atol=1e-7)
        np.testing.assert_allclose(targets[50]-targets[40], .1*direction, atol=1e-12)
        np.testing.assert_allclose(rotations[40:51], np.tile(np.eye(3), (11,1,1)), atol=1e-12)
        self.assertGreater(np.ptp(targets[:, 2]), .15)
        self.assertGreater(np.ptp(values[:, 0]), .1)
        for q, target, rotation in zip(values, targets, rotations):
            actual = forward(axes, q)
            np.testing.assert_allclose(actual[:3, :3] @ point + actual[:3, 3], target, atol=1e-7)
            np.testing.assert_allclose(actual[:3, :3], rotation, atol=1e-7)

    def test_solver_forward_transform_matches_exported_serial_frames(self):
        source, _ = fixture()
        source['nodes'][0].pop('translation')
        axes = [(np.array([.2, .1, .3]), np.array([0., 0, 1])),
                (np.array([-.1, .4, .5]), np.array([1., 0, 0]))]
        spec = {'id': 'test', 'nodes': [{'select': {'name': 'root'},
                'metadata': {'id': 'root', 'roles': ['assembly']}}], 'frames': [], 'joints': []}
        for i, (origin, axis) in enumerate(axes):
            parent = 'root' if i == 0 else f'link.{i-1}'
            spec['frames'].append({'parent': parent, 'metadata': {'id': f'link.{i}',
                'roles': ['arm']}, 'evidence': ['fixture']})
            spec['joints'].append({'id': f'joint.{i}', 'parent': parent, 'children': [f'link.{i}'],
                'type': 'revolute', 'axis': axis.tolist(), 'origin_m': origin.tolist(), 'evidence': ['fixture']})
        doc, binding = transform_asset(source, spec, 'hash')
        values = [.3, -.2]
        moved = apply_pose(doc, binding['joints'], {f'joint.{i}': q for i, q in enumerate(values)})
        index = next(n['node'] for n in binding['nodes'] if n['id'] == 'link.1')
        actual = {i: w for i, w, _ in scene_nodes(moved)}[index]
        np.testing.assert_allclose(actual, forward(axes, values), atol=1e-12)
