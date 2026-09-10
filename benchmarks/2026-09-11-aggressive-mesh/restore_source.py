# SPDX-License-Identifier: MIT OR Apache-2.0
"""Reconstruct a study input from archived unsimplified assets, never production."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[2]
source = root.parent / 'rm-simulator/local-assets/field'
output = root / 'out/tolerance-source'
recovered = json.loads(Path(__file__).with_name('recovered-inputs.json').read_text())
previous = json.loads((source / 'mesh-simplification.json').read_text())
shutil.copytree(source, output)
record = {}
for scope in ('', 'equipment'):
    mp = output / scope / 'manifest.json'
    manifest = json.loads(mp.read_text())
    sidepath = mp.parent / 'articulation.json'
    side = json.loads(sidepath.read_text())
    for name, entry in manifest['assets'].items():
        key = scope + '/' + name
        if key not in previous['assets']:
            continue
        for kind in ('visual', 'collision'):
            expected = previous['assets'][key][kind]['input_sha256']
            if expected in recovered:
                path = root / recovered[expected]
            else:
                archive = root.parent / 'assets/rm2026-reference.backup-1789058270939907000' / scope
                donor = json.loads((archive / 'manifest.json').read_text())['assets'][name]
                path = archive / donor[kind]
                expected = donor[kind + '_sha256']
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != expected:
                raise ValueError(f'archive mismatch: {path}')
            shutil.copy2(path, mp.parent / entry[kind])
            entry[kind + '_sha256'] = digest
            entry[kind + '_bytes'] = path.stat().st_size
            entry['triangles' if kind == 'visual' else 'collision_triangles'] = previous['assets'][key][kind]['before_triangles']
            if key in ('/resource-zone', 'equipment/tech-core'):
                entry['triangles' if kind == 'visual' else 'collision_triangles'] = donor['triangles' if kind == 'visual' else 'collision_triangles']
            if name in side['assets'] and kind in side['assets'][name].get('files', {}):
                side['assets'][name]['files'][kind]['sha256'] = digest
            record[key + '/' + kind] = dict(file=str(path), sha256=digest,
                exact_previous_input=digest == previous['assets'][key][kind]['input_sha256'])
        entry.pop('mesh_simplification', None)
        entry['collision_method'] = 'source-tessellation-v1'
    sidepath.write_text(json.dumps(side, indent=2) + '\n')
    manifest['articulation']['sha256'] = hashlib.sha256(sidepath.read_bytes()).hexdigest()
    manifest.pop('mesh_simplification', None)
    mp.write_text(json.dumps(manifest, indent=2) + '\n')
(output / 'mesh-simplification.json').unlink()
Path(__file__).with_name('source-record.json').write_text(json.dumps(record, indent=2) + '\n')
