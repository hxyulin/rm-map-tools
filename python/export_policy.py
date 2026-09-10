# SPDX-License-Identifier: MIT OR Apache-2.0
"""Export-time LOD policy. This module does not require a CAD kernel.

Print a preset with: python3 python/export_policy.py simulation
"""
import argparse
import copy
import json
import math
from pathlib import Path


def tolerance(linear_mm, angular_rad):
    return {'linear_deflection_mm': linear_mm, 'angular_deflection_rad': angular_rad}


def pair(visual, collision):
    return {'visual': tolerance(*visual), 'collision': tolerance(*collision)}


PRESETS = {
    'simulation': {
        'description': 'Interactive robot simulation; tighter terrain and articulated detail.',
        'defaults': pair((4.0, 0.5), (6.0, 0.65)),
        'parts': {'centre-logo-sheets': {'collision_enabled': False}},
        'assets': {
            **{name: pair((2.0, 0.35), (2.0, 0.35)) for name in
               ('floor', 'arena-static', 'fortress', 'centre-platform', 'undulating-road')},
            **{name: pair((1.0, 0.25), (2.0, 0.35)) for name in ('rune', 'outpost')},
        },
    },
    'preview': {
        'description': 'Small overview exports; inspect contact fidelity before physics use.',
        'defaults': pair((8.0, 0.8), (10.0, 0.9)), 'assets': {},
    },
    'vision': {
        'description': 'Closer views and optical details; larger visual meshes.',
        'defaults': pair((0.5, 0.15), (2.0, 0.35)), 'assets': {},
    },
    'legacy': {
        'description': 'Previous 2 mm / 0.35 rad tessellation with matching collision geometry.',
        'defaults': {**pair((2.0, 0.35), (2.0, 0.35)), 'collision_mode': 'visual'},
        'assets': {},
    },
}
KEYS = {'linear_deflection_mm', 'angular_deflection_rad'}


def validate_block(block, where):
    if not isinstance(block, dict) or set(block) - {'visual', 'collision', 'collision_mode', 'collision_enabled'}:
        raise ValueError(f'{where}: expected visual, collision, collision_mode or collision_enabled')
    if 'collision_enabled' in block and not isinstance(block['collision_enabled'], bool):
        raise ValueError(f'{where}: collision_enabled must be true or false')
    if 'collision_mode' in block and block['collision_mode'] not in ('separate', 'visual'):
        raise ValueError(f'{where}: collision_mode must be separate or visual')
    for kind in ('visual', 'collision'):
        if kind not in block:
            continue
        values = block[kind]
        if not isinstance(values, dict) or set(values) - KEYS:
            raise ValueError(f'{where}.{kind}: unknown tolerance field')
        for key, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{where}.{kind}.{key}: expected a finite positive number')
            if key == 'angular_deflection_rad' and value > math.pi:
                raise ValueError(f'{where}.{kind}.{key}: must be at most pi radians')


def merge(base, overlay):
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in ('visual', 'collision'):
            result.setdefault(key, {}).update(value)
        else:
            result[key] = value
    return result


class ExportPolicy:
    def __init__(self, preset=None, config=None, cli=None):
        if config is not None and not isinstance(config, dict):
            raise ValueError('policy must be a JSON object')
        preset = preset or (config or {}).get('preset', 'simulation')
        if not isinstance(preset, str) or preset not in PRESETS:
            raise ValueError(f'unknown preset {preset!r}')
        self.preset = preset
        self.config = copy.deepcopy(config or {})
        self.cli = copy.deepcopy(cli or {})
        if set(self.config) - {'schema_version', 'preset', 'defaults', 'assets', 'parts'}:
            raise ValueError('policy: unknown top-level field')
        if 'preset' in self.config and (not isinstance(self.config['preset'], str) or self.config['preset'] not in PRESETS):
            raise ValueError('policy: unknown preset')
        if type(self.config.get('schema_version', 1)) is not int or self.config.get('schema_version', 1) != 1:
            raise ValueError('policy: unsupported schema_version')
        validate_block(self.config.get('defaults', {}), 'defaults')
        validate_block(self.cli, 'command line')
        for group in ('assets', 'parts'):
            entries = self.config.get(group, {})
            if not isinstance(entries, dict):
                raise ValueError(f'{group}: expected a mapping of exact names to settings')
            for name, block in entries.items():
                if not isinstance(name, str) or not name:
                    raise ValueError(f'{group}: names must be nonempty strings')
                validate_block(block, f'{group}.{name}')
        self.resolved = {}

    def settings(self, asset, part=None):
        preset = PRESETS[self.preset]
        result = {'collision_mode': 'separate', 'collision_enabled': True, **copy.deepcopy(preset['defaults'])}
        for block in (preset['assets'].get(asset, {}), preset.get('parts', {}).get(part, {}),
                      self.config.get('defaults', {}),
                      self.cli, self.config.get('assets', {}).get(asset, {}),
                      self.config.get('parts', {}).get(part, {})):
            result = merge(result, block)
        if result['collision_mode'] == 'visual':
            result['collision'] = copy.deepcopy(result['visual'])
        if part is not None:
            self.resolved.setdefault(asset, {})[part] = copy.deepcopy(result)
        return result

    def metadata(self):
        return {'schema_version': 1, 'preset': self.preset,
                'overrides': copy.deepcopy(self.config), 'command_line': copy.deepcopy(self.cli),
                'resolved_parts': copy.deepcopy(self.resolved),
                'scope': 'Newly tessellated parts only; copied assets retain their input settings.'}


def add_arguments(parser):
    parser.add_argument('--preset', choices=PRESETS,
                        help='export-time LOD preset (default: policy preset or simulation)')
    parser.add_argument('--policy', type=Path, help='JSON settings with exact asset/part overrides')
    parser.add_argument('--lin', type=float, help='visual linear deflection in mm')
    parser.add_argument('--ang', type=float, help='visual angular deflection in radians')
    parser.add_argument('--collision-lin', type=float, help='collision linear deflection in mm')
    parser.add_argument('--collision-ang', type=float, help='collision angular deflection in radians')
    parser.add_argument('--collision-mode', choices=('separate', 'visual'),
                        help='independent source tessellation or reuse visual triangles')


def from_arguments(args, parser):
    cli = {}
    for kind, prefix in [('visual', ''), ('collision', 'collision_')]:
        values = {key: getattr(args, prefix + flag) for flag, key in
                  [('lin', 'linear_deflection_mm'), ('ang', 'angular_deflection_rad')]
                  if getattr(args, prefix + flag) is not None}
        if values:
            cli[kind] = values
    if args.collision_mode:
        cli['collision_mode'] = args.collision_mode
    try:
        config = json.loads(args.policy.read_text()) if args.policy else {}
        if not isinstance(config, dict):
            raise ValueError('policy must be a JSON object')
        return ExportPolicy(args.preset, config, cli)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('preset', choices=PRESETS, nargs='?', default='simulation')
    args = parser.parse_args()
    print(json.dumps(PRESETS[args.preset], indent=2))
