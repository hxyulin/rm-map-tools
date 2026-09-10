# SPDX-License-Identifier: MIT OR Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest
from export_job import build_commands
from export_policy import ExportPolicy


class ExportJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.job = self.root / 'job.json'
        self.config = {'schema_version': 1, 'stages': [
            {'type': 'field', 'package': 'input with spaces', 'index': 'input.npz',
             'equipment': 'equipment', 'out': 'field',
             'grafts': [{'package': 'donor', 'index': 'donor.npz', 'products': ['BREP_1', 'BREP_2']}]},
            {'type': 'elements', 'package': 'input', 'index': 'input.npz',
             'rules': 'rules.json', 'field': 'field', 'out': 'elements'},
            {'type': 'deploy', 'field': 'field', 'elements': 'elements', 'out': 'runtime'}]}

    def build(self):
        self.job.write_text(json.dumps(self.config))
        return build_commands(self.job, 'python')

    def test_job_paths_and_grafts_resolve_relative_to_file(self):
        commands = self.build()
        self.assertEqual(commands[0][2], str(self.root / 'input with spaces'))
        self.assertIn(str(self.root / 'donor') + ':' + str(self.root / 'donor.npz') + ':BREP_1,BREP_2', commands[0])
        self.assertIn('--field=' + str(self.root / 'field'), commands[1])
        self.assertIn('--out=' + str(self.root / 'runtime'), commands[2])

    def test_typo_existing_and_overlapping_outputs_fail_before_running(self):
        self.config['stages'][1]['typo'] = 1
        with self.assertRaises(ValueError): self.build()
        del self.config['stages'][1]['typo']
        self.config['stages'][2]['out'] = 'field/nested'
        with self.assertRaises(ValueError): self.build()
        self.config['stages'][2]['out'] = 'runtime'
        (self.root / 'field').mkdir()
        with self.assertRaises(ValueError): self.build()

    def test_policy_is_validated_and_only_sent_to_tessellating_stages(self):
        policy = self.root / 'policy.json'
        self.config['policy'] = policy.name
        policy.write_text('{"preset":"preview"}')
        commands = self.build()
        self.assertIn('--policy', commands[0])
        self.assertIn('--policy', commands[1])
        self.assertNotIn('--policy', commands[2])
        policy.write_text('{"preset":"typo"}')
        with self.assertRaises(ValueError): self.build()

    def test_policy_file_can_select_preset_and_explicit_cli_wins(self):
        self.assertEqual(ExportPolicy(config={'preset': 'vision'}).preset, 'vision')
        self.assertEqual(ExportPolicy('preview', config={'preset': 'vision'}).preset, 'preview')
        for value in [[], {}, False, 3, 'typo']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExportPolicy(config={'preset': value})


if __name__ == '__main__':
    unittest.main()
