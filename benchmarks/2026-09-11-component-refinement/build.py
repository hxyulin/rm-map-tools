# SPDX-License-Identifier: MIT OR Apache-2.0
"""Rebuild base and resource meshes from source with component refinement."""
import copy
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, write_glb
from extract_entities import partition
from simplify_package import digest, simplify_glb, scene_triangles
from texture_atlas import export_atlas
from collision_artwork import export_collision_artwork
from select_resource_units import select

root = Path('out/component-refinement-candidate').resolve()
current = Path('../rm-simulator/local-assets/field').resolve()
source = Path('out/tolerance-source').resolve()
shutil.copytree(current, root)
report = {}
manifest_path = root / 'manifest.json'
manifest = json.loads(manifest_path.read_text())
entry = manifest['assets']['resource-zone']
source_manifest = json.loads((source / 'manifest.json').read_text())
resource_inputs = {}
for kind in ('visual', 'collision'):
    original = source_manifest['assets']['resource-zone']
    path = source / original[kind]
    assert digest(path) == original[kind + '_sha256']
    raw = select(path)
    doc, binary = read_glb(path)
    pieces = partition(doc, binary, raw)
    remainder, payload = pieces[0]
    # Exact partition conservation is also asserted by partition().
    resource_inputs[kind] = {'sha256': digest(path), 'source_triangles': scene_triangles(doc),
                             'unit_triangles_removed': sum(scene_triangles(d) for d, _ in pieces[1:]), 'entities': raw}
    dest = root / entry[kind]
    write_glb(dest, remainder, payload)
    shutil.copy2(dest, root.parent / ('resource-refinement-source-' + kind + '.glb'))
    stats = simplify_glb(dest, 4, sampled_limit_mm=12 if kind == 'visual' else 8,
                         deviation_samples=4096, lock_borders=False,
                         preserve=[{'node': 'source_13267852_7000001_1_6', 'primitive': 0}] if kind == 'visual' else ())
    report['resource-zone:' + kind] = stats
    entry[kind + '_sha256'] = digest(dest)
    entry[kind + '_bytes'] = dest.stat().st_size
    entry['triangles' if kind == 'visual' else 'collision_triangles'] = stats['after_triangles']
    entry.setdefault('mesh_simplification', {})[kind] = {k: v for k, v in stats.items() if k != 'primitives'}
    if kind == 'collision':
        entry['collision_method'] = stats['method']
    print('resource-zone', kind, stats['before_triangles'], '->', stats['after_triangles'], flush=True)
entry['entity_partition']['simplification_metadata_scope'] = 'remaining resource-zone after unit extraction'
(root / 'resource-source-partition.json').write_text(json.dumps({'inputs': resource_inputs,
    'evidence': 'Whole source components within the six audited unit envelopes; source shafts and socket primitives retained. Standalone unit assets stay unchanged.'}, indent=2) + '\n')
entry['source_partition'] = {'file': 'resource-source-partition.json', 'sha256': digest(root / 'resource-source-partition.json')}
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

# Restore base source and refresh input pins before the existing artwork pipeline.
base = root / 'equipment'; mp = base / 'manifest.json'
m = json.loads(mp.read_text()); e = m['assets']['base']
m.pop('texture_atlas', None)  # Source restoration replaces the prior baked atlas.
original = json.loads((source / 'equipment/manifest.json').read_text())['assets']['base']
artpath = base / m['articulation']['file']; art = json.loads(artpath.read_text())
for kind in ('visual', 'collision'):
    p = source / 'equipment' / original[kind]
    assert digest(p) == original[kind + '_sha256']
    shutil.copy2(p, base / e[kind])
    e[kind + '_sha256'] = digest(p)
    e.get('mesh_simplification', {}).pop(kind, None)
    art['assets']['base']['files'][kind]['sha256'] = digest(p)
e['collision_method'] = 'source-tessellation-v1'
artpath.write_text(json.dumps(art, indent=2) + '\n'); m['articulation']['sha256'] = digest(artpath)
mp.write_text(json.dumps(m, indent=2) + '\n')
config = dict(schema_version=1, render_mode='embedded', pixels_per_metre=4096, atlas_size=2048,
              merge_distance_m=0, files={'base.glb': [dict(node='source_13267588_001_1_1', material='colour_1.0000,1.0000,1.0000')]},
              simplify={'base.glb': dict(error_mm=4, sampled_limit_mm=12, deviation_samples=4096, lock_borders=False)})
rules = root / 'base-refinement-atlas-rules.json'; rules.write_text(json.dumps(config, indent=2))
print('base visual', flush=True)
export_atlas(base, rules)
print('base collision', flush=True)
export_collision_artwork(base, 'base.glb', config['files']['base.glb'],
                         dict(error_mm=4, sampled_limit_mm=8, deviation_samples=4096, lock_borders=False))
report['base'] = json.loads(mp.read_text())['assets']['base']['mesh_simplification']
(root / 'component-refinement-report.json').write_text(json.dumps(report, indent=2) + '\n')
print('complete', flush=True)
