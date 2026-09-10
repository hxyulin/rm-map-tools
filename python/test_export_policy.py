# SPDX-License-Identifier: MIT OR Apache-2.0
import argparse
import unittest
from export_policy import ExportPolicy, add_arguments, from_arguments


class PolicyTests(unittest.TestCase):
    def test_simulation_preserves_terrain_and_separates_equipment(self):
        p = ExportPolicy()
        equipment = p.settings('resource-zone', 'panel')
        self.assertGreater(equipment['collision']['linear_deflection_mm'],
                           equipment['visual']['linear_deflection_mm'])
        terrain = p.settings('undulating-road', 'BREP_220')
        self.assertEqual(terrain['collision']['linear_deflection_mm'], 2)
        self.assertEqual(terrain['visual'], terrain['collision'])

    def test_overrides_are_independent_and_specific_names_win(self):
        p = ExportPolicy(config={'assets': {'base': {'visual': {'linear_deflection_mm': 3}}},
                                 'parts': {'screw': {'collision': {'angular_deflection_rad': 0.4}}}},
                         cli={'visual': {'linear_deflection_mm': 5}})
        x = p.settings('base', 'screw')
        self.assertEqual(x['visual']['linear_deflection_mm'], 3)
        self.assertEqual(x['collision']['angular_deflection_rad'], 0.4)
        self.assertEqual(p.settings('dart-station')['visual']['linear_deflection_mm'], 5)
        self.assertEqual(p.metadata()['resolved_parts']['base']['screw'], x)
        x['collision']['angular_deflection_rad'] = 999
        self.assertEqual(p.metadata()['resolved_parts']['base']['screw']['collision']['angular_deflection_rad'], 0.4)

    def test_visual_mode_and_legacy_reuse_final_visual_settings(self):
        x = ExportPolicy('legacy', cli={'visual': {'linear_deflection_mm': 3}}).settings('base')
        self.assertEqual(x['visual'], x['collision'])
        self.assertEqual(x['collision_mode'], 'visual')

    def test_invalid_numbers_and_typos_fail_before_export(self):
        for value in [0, -1, float('nan'), float('inf'), True, '2']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ExportPolicy(config={'defaults': {'visual': {'linear_deflection_mm': value}}})
        for config in [{'typo': {}}, {'schema_version': 2}, {'assets': []},
                       {'defaults': {'visual': {'lin': 3}}},
                       {'defaults': {'collision': {'angular_deflection_rad': 4}}}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                ExportPolicy(config=config)

    def test_cli_resolves_units_without_requiring_occt(self):
        parser = argparse.ArgumentParser()
        add_arguments(parser)
        args = parser.parse_args(['--lin', '3', '--collision-ang', '0.6'])
        x = from_arguments(args, parser).settings('base')
        self.assertEqual(x['visual']['linear_deflection_mm'], 3)
        self.assertEqual(x['collision']['angular_deflection_rad'], 0.6)


if __name__ == '__main__':
    unittest.main()
