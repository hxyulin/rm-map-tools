# SPDX-License-Identifier: MIT OR Apache-2.0
"""Protection follows ownership through neutral meshes and batched descendants."""
import json
import unittest
from guard import protected_nodes, POLICY


class FidelityOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY.read_text())

    def test_tool_head_includes_neutral_descendant_and_late_batch(self):
        doc = {'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [
            {'children': [1, 2]},
            {'extras': {'component_id': 'technology-core/tool-head'}, 'children': [3]},
            {'extras': {'component_id': 'technology-core/arm-and-shared'}, 'children': [4]},
            {'name': 'neutral-reconstructed-batch', 'mesh': 0},
            {'name': 'unprotected-arm-cover', 'mesh': 0}]}
        self.assertEqual(protected_nodes(doc, 'tech-core', self.policy), {1, 3})

    def test_complete_armor_body_context_survives_child_batches(self):
        doc = {'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [
            {'children': [1, 2]},
            {'name': 'source_body_4099408', 'children': [3]},
            {'name': 'source_body_4275783', 'mesh': 0},
            {'name': 'neutral-housing', 'mesh': 0}]}
        self.assertEqual(protected_nodes(doc, 'base', self.policy), {1, 3})

    def test_rune_all_nodes_are_protected(self):
        doc = {'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [
            {'children': [1]}, {'mesh': 0}]}
        self.assertEqual(protected_nodes(doc, 'rune', self.policy), {0, 1})

    def test_base_neutral_source_shell_is_protected(self):
        doc = {'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [
            {'children': [1, 2]},
            {'extras': {'source_unit_id': 4723785}, 'children': [3]},
            {'extras': {'source_unit_id': 4275783}, 'mesh': 0},
            {'name': 'neutral-shell-batch', 'mesh': 0}]}
        self.assertEqual(protected_nodes(doc, 'base', self.policy), {1, 3})


if __name__ == '__main__':
    unittest.main()
