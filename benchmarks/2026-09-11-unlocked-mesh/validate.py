# SPDX-License-Identifier: MIT OR Apache-2.0
"""Check the deployed candidate against its unsimplified package and old terrain."""
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, accessor

root = Path(__file__).resolve().parents[2]
source = root.parent / 'assets/rm2026-simulation-source'
output = root / 'out/unlocked-default'
before = root.parent / 'rm-simulator/local-assets/field'
config = json.loads(Path(__file__).with_name('default.json').read_text())
report = {'unchanged_terrain': [], 'preserved_visuals': [], 'unchanged_sidecars_except_hashes': [], 'deviations_mm': {}}
def without_hashes(value):
    if isinstance(value, dict):
        return {k: without_hashes(v) for k,v in value.items() if k != 'sha256'}
    if isinstance(value, list):
        return [without_hashes(v) for v in value]
    return value
for scope in ('', 'equipment'):
    manifest = json.loads((output / scope / 'manifest.json').read_text())
    for name, entry in manifest['assets'].items():
        settings = config['assets'].get(name, {})
        if not settings.get('enabled', True):
            for kind in ('visual', 'collision'):
                relative = str(Path(scope) / entry[kind])
                assert (before / relative).read_bytes() == (output / relative).read_bytes()
                report['unchanged_terrain'].append(relative)
        for selector in settings.get('visual_preserve', []):
            original, original_bin = read_glb(source / scope / entry['visual'])
            changed, changed_bin = read_glb(output / scope / entry['visual'])
            def geometry(doc, binary):
                node = next(n for n in doc['nodes'] if n.get('name') == selector['node'])
                p = doc['meshes'][node['mesh']]['primitives'][selector['primitive']]
                positions = accessor(doc, binary, p['attributes']['POSITION'])
                indices = accessor(doc, binary, p['indices']).reshape(-1) if 'indices' in p else np.arange(len(positions))
                return positions[indices]
            assert np.array_equal(geometry(original, original_bin), geometry(changed, changed_bin))
            report['preserved_visuals'].append({'asset':name, **selector})
        if 'mesh_simplification' in entry:
            report['deviations_mm'][name] = {}
            for kind, record in entry['mesh_simplification'].items():
                assert record['deviation_triangles_per_direction'] == 4096
                assert record['max_sampled_deviation_mm'] <= record['sampled_deviation_limit_mm']
                report['deviations_mm'][name][kind] = record['max_sampled_deviation_mm']
for sidecar in source.rglob('articulation.json'):
    relative = sidecar.relative_to(source)
    assert without_hashes(json.loads(sidecar.read_text())) == without_hashes(json.loads((output / relative).read_text()))
    report['unchanged_sidecars_except_hashes'].append(str(relative))
Path(__file__).with_name('validation.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
