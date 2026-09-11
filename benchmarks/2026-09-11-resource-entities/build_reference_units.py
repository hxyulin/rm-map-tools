# SPDX-License-Identifier: MIT OR Apache-2.0
"""Correct shaft ownership and use the standalone STEP for shared energy units.

Inputs: pre-extraction package, audited selection JSON, standalone STEP, new output.
CAD coordinates here are the audited mounting frame, not generated geometry.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
from scipy.spatial.transform import Rotation
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from extract_entities import run, digest
from export_field_package import GlbWriter
from mesh_parts import tessellate
from simplify_package import simplify_glb
from validate_parts import read_part


def build(package, selection, step, output):
    rules = json.loads(selection.read_text())
    returned = {}
    for entity in rules['entities']:
        for kind in ('visual', 'collision'):
            # Main silver shaft and its fasteners, plus turquoise socket faces.
            parts = entity[kind]
            keep = [p for p in parts if not (p['node'] == 'source_13267862_7000001_1_16' and p['primitive'] in (0, 6))]
            returned[entity['id'] + ':' + kind] = sum(hi - lo for p in parts if p not in keep for lo, hi in p['triangle_ranges'])
            assert returned[entity['id'] + ':' + kind] > 0
            entity[kind] = keep
    rules['evidence'] = ['Corrected using standalone energy-unit STEP. Silver inserted shafts and turquoise socket faces stay on the resource hub.',
                         'Units use standalone geometry after partition; unit dimensions are 150 mm long and 95 mm maximum diameter.']
    run(package, rules, output)
    # First verify the corrected partition before replacing unit geometry.
    import subprocess
    check = subprocess.run([sys.executable, str(Path(__file__).with_name('validate.py')), str(package), str(output)], check=True, capture_output=True, text=True)
    partition_check = json.loads(check.stdout)
    doc, _, error = read_part(str(step))
    if error:
        raise ValueError(error)
    points, triangles, colors, keys = tessellate(doc, .2, .15)
    angle = np.pi / 6
    rotation = np.array([[np.cos(angle), 0, np.sin(angle)],
                         [np.sin(angle), 0, -np.cos(angle)], [0, 1, 0]])
    local = points / 1000 @ rotation.T + [0, 0, -.075]
    writer = GlbWriter('ENERGY-UNIT', {'version': '2.0', 'generator': 'rm-map-tools standalone energy-unit STEP'})
    writer.add_node('standalone-energy-unit', local, triangles, [keys[c] for c in colors])
    path = output / 'energy-unit.glb'
    writer.write(path)
    source_mesh_sha = digest(path)
    with tempfile.TemporaryDirectory() as tmp:
        import shutil
        reference = Path(tmp) / 'source.glb'; shutil.copy2(path, reference)
        stats = simplify_glb(path, .25, sampled_limit_mm=.75, deviation_samples=4096, lock_borders=False)
        # Preserve the tessellated reference locally alongside the package for review.
        shutil.copy2(reference, output.parent / (output.name + '-energy-unit-reference.glb'))
    stats.pop('primitives', None)
    stats['input_sha256'] = source_mesh_sha
    import shutil
    shutil.copy2(path, output / 'energy-unit-collision.glb')
    manifest = json.loads((output / 'manifest.json').read_text())
    for i, entity in enumerate(rules['entities']):
        entry = manifest['assets'][entity['id']]
        for kind in ('visual', 'collision'):
            old = output / entry[kind]
            new = 'energy-unit' + ('-collision' if kind == 'collision' else '') + '.glb'
            entry[kind] = new
            entry[kind + '_sha256'] = digest(output / new)
            entry[kind + '_bytes'] = (output / new).stat().st_size
            entry['triangles' if kind == 'visual' else 'collision_triangles'] = stats['after_triangles']
            old.unlink()
        entry['collision_method'] = stats['method']
        entry['mesh_simplification'] = {'visual': copy.deepcopy(stats), 'collision': copy.deepcopy(stats)}
        entry['entity_partition']['geometry_source'] = 'standalone energy-unit STEP'
        entry['entity_partition']['simplification_metadata_scope'] = 'standalone unit'
        r = Rotation.from_rotvec([-i * np.pi / 3, 0, 0]).as_matrix()
        for placement in entry['placements_in_source_arena_frame']:
            m = np.asarray(placement['matrix_local_to_arena'])
            m[:3, :3] = m[:3, :3] @ r
            placement['matrix_local_to_arena'] = m.tolist()
            placement['rotation_xyzw'] = Rotation.from_matrix(m[:3, :3]).as_quat().tolist()
        entry['bbox_local_m'] = [local.min(0).tolist(), local.max(0).tolist()]
    report = {'standalone_step': step.name, 'standalone_step_sha256': digest(step),
              'tessellation': {'linear_deflection_mm': .2, 'angular_deflection_rad': .15},
              'simplification': stats, 'returned_to_resource_zone': returned,
              'partition_before_replacement': partition_check,
              'shared_mesh': 'energy-unit.glb', 'placed_units': 12,
              'placement': 'Existing unit centers; top unit aligned by +30 degree roll of STEP, then six 60 degree radial rotations.'}
    (output / 'energy-unit-reference.json').write_text(json.dumps(report, indent=2) + '\n')
    manifest['energy_unit_reference'] = {'file': 'energy-unit-reference.json', 'sha256': digest(output / 'energy-unit-reference.json')}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('package', 'selection', 'step', 'output'):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    print(json.dumps(build(a.package, a.selection, a.step, a.output), indent=2))
