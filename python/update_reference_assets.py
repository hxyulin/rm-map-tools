# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build this repository's semantic reference package, separate from simulator assets."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from export_semantics import annotate_package, digest, safe_path

REPO = Path(__file__).resolve().parent.parent


def verify_package(root):
    """Check every declared GLB and sidecar before publishing the reference."""
    manifest = json.loads((root / 'manifest.json').read_text())
    for entry in manifest['assets'].values():
        for kind in ('visual', 'collision'):
            if kind in entry and digest(safe_path(root, entry[kind])) != entry[kind + '_sha256']:
                raise ValueError(f'{root}: {kind} checksum mismatch')
    if 'articulation' in manifest:
        entry = manifest['articulation']
        if digest(safe_path(root, entry['file'])) != entry['sha256']:
            raise ValueError(f'{root}: articulation checksum mismatch')
    return manifest


def build_reference(field, out, field_rules, equipment_rules, index, replace=False):
    field, out = Path(field).resolve(), Path(out).resolve()
    if out == field or out.is_relative_to(field) or field.is_relative_to(out):
        raise ValueError('reference and simulator source directories must be separate')
    if out.exists() and not replace:
        raise ValueError(f'{out} exists; use --replace to retain it as a backup')
    verify_package(field)
    verify_package(field / 'equipment')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.reference-', dir=out.parent) as directory:
        stage = Path(directory) / 'package'
        shutil.copytree(field, stage)
        inputs = {}
        for key, rules_path, target in [('field', field_rules, stage),
                                        ('equipment', equipment_rules, stage / 'equipment')]:
            rules_path = Path(rules_path)
            annotate_package(target, json.loads(rules_path.read_text()), digest(rules_path), geometry_source_root=field)
            inputs[key] = {'rules': os.path.relpath(rules_path.resolve(), REPO),
                           'rules_sha256': digest(rules_path),
                           'source_manifest_sha256': digest((field if key == 'field' else field / 'equipment') / 'manifest.json')}
        manifest = verify_package(stage)
        verify_package(stage / 'equipment')
        manifest['reference_equipment'] = {'file': 'equipment/manifest.json',
                                           'sha256': digest(stage / 'equipment/manifest.json')}
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        record = {'schema_version': 1, 'directory': os.path.relpath(out, REPO),
                  'purpose': 'rm-map-tools semantic reference; requires a sidecar-aware consumer for motion',
                  'manifest_sha256': digest(stage / 'manifest.json'),
                  'equipment_manifest_sha256': digest(stage / 'equipment/manifest.json'),
                  'inputs': inputs,
                  'assets': {}}
        for key, root in [('field', stage), ('equipment', stage / 'equipment')]:
            sidecar = json.loads((root / 'articulation.json').read_text())
            for name, asset in sidecar['assets'].items():
                visual = asset['files']['visual']
                record['assets'][f'{key}/{name}'] = {
                    'visual_sha256': visual['sha256'],
                    'joints': [j['id'] for j in visual['joints']],
                    'pending': visual['pending']}
        (stage / 'reference.json').write_text(json.dumps(record, indent=2) + '\n')
        backup = None
        if out.exists():
            backup = out.with_name(out.name + f'.backup-{time.time_ns()}')
            out.rename(backup)
        try:
            stage.rename(out)
        except BaseException:
            if backup is not None:
                backup.rename(out)
            raise
    index = Path(index)
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(record, indent=2) + '\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field', type=Path, default=REPO.parent / 'assets/rm2026-field')
    parser.add_argument('--out', type=Path, default=REPO.parent / 'assets/rm2026-reference')
    parser.add_argument('--field-rules', type=Path, default=REPO / 'rules/semantics-legacy-field.json')
    parser.add_argument('--equipment-rules', type=Path, default=REPO / 'rules/semantics-legacy-equipment.json')
    parser.add_argument('--index', type=Path, default=REPO / 'source/REFERENCE_ASSETS.json')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    result = build_reference(args.field, args.out, args.field_rules, args.equipment_rules, args.index, args.replace)
    print(f'Updated {result["directory"]} and {args.index}')


if __name__ == '__main__':
    main()
