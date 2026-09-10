# SPDX-License-Identifier: MIT OR Apache-2.0
"""Keep the two unavailable original assets at their deployed versions for study."""
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[2]
source = root / 'out/tolerance-source'
output = root / 'out/tolerance-matched-source'
pinned = json.loads(Path(__file__).with_name('deployed-input-hashes.json').read_text())
shutil.copytree(source, output)
for scope, name in [('', 'resource-zone'), ('equipment', 'tech-core')]:
    deployed = root.parent / 'rm-simulator/local-assets/field' / scope
    entry = json.loads((deployed / 'manifest.json').read_text())['assets'][name]
    manifest_path = output / scope / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['assets'][name] = entry
    for kind in ('visual', 'collision'):
        path = deployed / entry[kind]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != pinned[name][kind] or digest != entry[kind + '_sha256']:
            raise ValueError(f'{name}/{kind}: deployed asset changed')
        shutil.copy2(path, manifest_path.parent / entry[kind])
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
