#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check real-source coverage, rest geometry, materials and linkage closure."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from assemble import collect, digest, frames

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import accessor, mesh_instances, read_glb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--recipe', type=Path, default=Path(__file__).with_name('recipe.json'))
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    parts, inventory = collect(args.sources, recipe)
    expected = {p['name']: p for p in parts}
    document, binary = read_glb(args.package / 'neutral.glb')
    count = 0;seen = set();maximum_error = 0
    for ni, pi, p, t, material in mesh_instances(document, binary):
        name = document['nodes'][ni]['name'];part = expected[name]
        assert name not in seen;seen.add(name)
        original = part['points'][part['triangles']] + recipe['links'][part['link']]['origin_gltf_m']
        assert p[t].shape == original.shape
        error = float(np.abs(p[t] - original).max())
        maximum_error = max(error, maximum_error)
        assert error < 2e-7, (name, error)
        extra = document['nodes'][ni]['extras']
        assert extra == part['extras']
        # Compare material factors with their actual source, including fallback provenance.
        source_id = extra.get('source_id')
        if source_id:
            sd, sb = read_glb(args.sources / recipe['sources'][source_id]['visual']['file']) if source_id not in source_cache else source_cache[source_id]
            source_cache[source_id] = (sd, sb)
            sid = extra['native_solid_index']
            sn = next(n for n in sd['nodes'] if n.get('extras', {}).get('native_solid_index') == sid)
            primitive = int(name.rsplit('-', 1)[1]);sm = sd['materials'][sd['meshes'][sn['mesh']]['primitives'][primitive]['material']]
            assert document['materials'][material] == sm, name
        count += len(t)
    assert seen == expected.keys()
    # A parallelogram must keep both ends of its connecting rod on their pins.
    rest = frames(recipe['links']);rod = rest['pitch-rod'][:3, 3]
    p0 = rest['pitch'][:3, 3];c0 = rest['pitch-crank'][:3, 3]
    offset = rod - c0;upper = p0 + offset;maximum_closure = 0;minimum_gap = float('inf')
    chassis_top = max((part['points'] + recipe['links'][part['link']]['origin_gltf_m'])[:, 1].max()
                      for part in parts if part['extras'].get('source_id') == 'chassis')
    for yaw in np.linspace(-np.pi, np.pi, 13):
        for pitch in np.linspace(-.2, .35, 23):
            f = frames(recipe['links'], {'yaw_rad': float(yaw), 'pitch_rad': float(pitch)})
            upper_from_pitch = f['pitch'][:3, :3] @ (upper - p0) + f['pitch'][:3, 3]
            upper_from_rod = f['pitch-rod'][:3, :3] @ (upper - rod) + f['pitch-rod'][:3, 3]
            error = np.linalg.norm(upper_from_pitch - upper_from_rod)
            maximum_closure = max(maximum_closure, float(error))
            assert error < 1e-10
            if yaw == -np.pi:  # yaw preserves height; test the full pitch interval.
                low = min((part['points'] @ f[part['link']][:3, :3].T + f[part['link']][:3, 3])[:, 1].min()
                          for part in parts if part['link'] in ['yaw', 'pitch', 'pitch-crank', 'pitch-rod'])
                minimum_gap = min(minimum_gap, float(low - chassis_top))
    assert minimum_gap > .035
    animated, data = read_glb(args.package / 'animated.glb')
    channels = animated['animations'][0]['channels']
    assert len(channels) == 8
    for channel in channels:
        target = animated['nodes'][channel['target']['node']]
        assert 'matrix' not in target
        sampler = animated['animations'][0]['samplers'][channel['sampler']]
        values = accessor(animated, data, sampler['output'])
        assert np.isfinite(values).all()
        np.testing.assert_allclose(np.linalg.norm(values, axis=1), 1, atol=1e-7, rtol=0)
    manifest = json.loads((args.package / 'manifest.json').read_text())
    assert manifest['recipe_sha256'] == digest(args.recipe)
    assert manifest['sources'] == recipe['sources']
    assert manifest['placed_triangles'] == count
    assert manifest['inventory'] == inventory
    for spec in manifest['files'].values():assert digest(args.package / spec['file']) == spec['sha256']
    result = {'placed_triangles': count, 'retained_geometry_parts': len(seen),
              'maximum_float32_rest_coordinate_error_m': maximum_error,
              'source_materials_and_metadata_preserved': True,
              'pitch_linkage_samples': 13 * 23, 'maximum_pitch_linkage_closure_error_m': maximum_closure,
              'minimum_moving_gimbal_vertical_gap_above_chassis_m': minimum_gap,
              'animated_motion_channels': len(channels),
              'scope': 'Geometry/metadata and kinematic visual checks. No certification of fixed integration interference, feed compatibility, manufacturing, collision, scoring, mass or suspension dynamics.'}
    (args.package / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


source_cache = {}
if __name__ == '__main__':
    main()
