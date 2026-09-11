#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Run an export pipeline from JSON. Paths are relative to the job file.

Usage: ocpenv/bin/python python/export_job.py rules/export-job.example.json [--dry-run]
The job chooses stages, input/output paths and a shared tessellation policy.
Commands run without a shell, stop on failure, and require new output paths.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

from export_policy import ExportPolicy

SCRIPTS = {
    'field': 'export_field_package.py',
    'elements': 'export_elements.py',
    'semantics': 'export_semantics.py',
    'deploy': 'deploy_field.py',
}
REQUIRED = {
    'field': {'package', 'index', 'equipment', 'out'},
    'elements': {'package', 'index', 'rules', 'field', 'out'},
    'semantics': {'package', 'rules', 'out'},
    'deploy': {'field', 'elements', 'out'},
}
OPTIONAL = {
    'field': {'floor', 'arena_products', 'grafts', 'graft_floor', 'graft_colours', 'texture_atlas'},
    'elements': {'semantics', 'graft', 'graft_floor', 'graft_colours', 'texture_atlas'},
    'semantics': set(), 'deploy': set(),
}
PATHS = {'package', 'index', 'equipment', 'out', 'rules', 'field', 'elements', 'semantics', 'texture_atlas'}


def build_commands(job_path, interpreter=None):
    job_path = Path(job_path).resolve()
    base = job_path.parent
    job = json.loads(job_path.read_text())
    if not isinstance(job, dict) or set(job) - {'schema_version', 'policy', 'stages'} or type(job.get('schema_version')) is not int or job['schema_version'] != 1:
        raise ValueError('job: expected schema_version 1 and known fields')

    def path(value):
        if not isinstance(value, str) or not value:
            raise ValueError('expected nonempty path string')
        return str((base / Path(value).expanduser()).resolve())

    policy = path(job['policy']) if 'policy' in job else None
    if policy:
        ExportPolicy(config=json.loads(Path(policy).read_text()))
    stages = job.get('stages')
    if not isinstance(stages, list) or not stages:
        raise ValueError('stages: expected nonempty list')
    commands = []
    outputs = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get('type'), str) or stage['type'] not in SCRIPTS:
            raise ValueError('stage: expected field, elements, semantics or deploy')
        kind = stage['type']
        keys = set(stage) - {'type'}
        if keys - REQUIRED[kind] - OPTIONAL[kind] or REQUIRED[kind] - keys:
            raise ValueError(f'{kind}: required {sorted(REQUIRED[kind])}; optional {sorted(OPTIONAL[kind])}')
        cmd = [interpreter or sys.executable, str(Path(__file__).with_name(SCRIPTS[kind]))]
        positional = ['package', 'index'] if kind in ('field', 'elements') else ['package'] if kind == 'semantics' else []
        for key in positional:
            cmd.append(path(stage[key]))
        if policy and kind in ('field', 'elements'):
            cmd += ['--policy', policy]
        for key, value in stage.items():
            if key == 'type' or key in positional:
                continue
            if key in ('graft', 'grafts'):
                grafts = value if key == 'grafts' else [value]
                if not isinstance(grafts, list):
                    raise ValueError('grafts: expected list')
                for graft in grafts:
                    expected = {'package', 'index', 'products'} if kind == 'field' else {'package', 'index'}
                    if not isinstance(graft, dict) or set(graft) != expected:
                        raise ValueError(f'{kind} graft: expected {sorted(expected)}')
                    pieces = [path(graft['package']), path(graft['index'])]
                    if any(':' in p for p in pieces):
                        raise ValueError('graft paths cannot contain colon')
                    if kind == 'field':
                        products = graft['products']
                        if not isinstance(products, list) or not products or any(not isinstance(p, str) or not p or ',' in p or ':' in p for p in products):
                            raise ValueError('graft products: expected nonempty product name list')
                        pieces.append(','.join(products))
                    cmd += ['--graft', ':'.join(pieces)]
                continue
            if key in PATHS:
                value = path(value)
            elif key == 'arena_products':
                if not isinstance(value, list) or any(not isinstance(p, str) or not p or ',' in p for p in value):
                    raise ValueError('arena_products: expected list of product names')
                value = ','.join(value)
            elif not isinstance(value, str) or not value:
                raise ValueError(f'{key}: expected nonempty string')
            # Equals also makes a literal leading '-' safe as an option value.
            cmd.append('--' + key.replace('_', '-') + '=' + value)
        output = Path(path(stage['out']))
        if output.exists():
            raise ValueError(f'output already exists: {output}')
        if any(output == other or output.is_relative_to(other) or other.is_relative_to(output) for other in outputs):
            raise ValueError(f'overlapping stage outputs: {output}')
        outputs.append(output)
        commands.append(cmd)
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='validate the job and print commands')
    args = parser.parse_args()
    try:
        commands = build_commands(args.job)
        for command in commands:
            print(shlex.join(command), flush=True)
            if not args.dry_run:
                subprocess.run(command, check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
