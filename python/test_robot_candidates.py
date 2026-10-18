# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source ownership survives candidate packaging, including separate open shells."""
import copy
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'benchmarks/2026-10-18-team-robot/package_candidates.py'
spec = importlib.util.spec_from_file_location('robot_candidates', SCRIPT)
candidates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidates)


class CandidateOwnershipTests(unittest.TestCase):
    def fixture(self):
        rows = [
            {'path': '1', 'name': 'robot', 'occurrence_name': 'root', 'children': ['1/1', '1/2', '1/3']},
            {'path': '1/1', 'name': 'solid', 'occurrence_name': 'a', 'native_solids': [7]},
            {'path': '1/2', 'name': 'shell', 'occurrence_name': 'b', 'native_solids': []},
            {'path': '1/3', 'name': 'alias', 'occurrence_name': 'c', 'native_solids': [7]},
        ]
        document = {'nodes': [
            {'name': 'root', 'children': [1, 2]},
            {'mesh': 0, 'extras': {'native_solid_index': 7}},
            {'mesh': 1, 'extras': {'native_solid_index': 0, 'source_leaf_path': '1/2'}},
        ], 'meshes': [{'name': 'solid'}, {'name': 'shell'}]}
        return rows, document

    def test_shell_attaches_to_its_leaf_and_solid_alias_does_not_duplicate_geometry(self):
        rows, document = self.fixture()
        meshes = copy.deepcopy(document['meshes'])
        self.assertEqual(candidates.attach_source_meshes(document, rows), [])
        self.assertEqual(document['nodes'][1]['extras']['source_occurrence_paths'], ['1/1', '1/3'])
        self.assertEqual(document['nodes'][2]['extras']['source_occurrence_paths'], ['1/2'])
        self.assertEqual(document['nodes'][5]['children'], [2])
        self.assertEqual(document['nodes'][6]['children'], [])
        self.assertEqual(document['meshes'], meshes)
        for index in [1, 2]:
            self.assertEqual(sum(n.get('children', []).count(index) for n in document['nodes']), 1)

    def test_legacy_aggregated_shell_is_retained_at_root(self):
        rows, document = self.fixture()
        del document['nodes'][2]['extras']['source_leaf_path']
        self.assertEqual(candidates.attach_source_meshes(document, rows), [0])
        self.assertIn(2, document['nodes'][0]['children'])

    def test_invalid_shell_membership_is_rejected(self):
        for path in ['1', 'missing']:
            with self.subTest(path=path):
                rows, document = self.fixture()
                document['nodes'][2]['extras']['source_leaf_path'] = path
                with self.assertRaisesRegex(ValueError, 'audited non-solid leaf'):
                    candidates.attach_source_meshes(document, rows)


if __name__ == '__main__':
    unittest.main()
