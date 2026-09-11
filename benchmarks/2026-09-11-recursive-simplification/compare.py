# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compare repeated passes with higher tolerances, measuring against source."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, write_glb, mesh_instances
from collision_artwork import strip
from simplify_package import simplify_glb, scene_triangles, digest
from mesh_quality import deviation
from attach_texture_atlas import attach


def parts(path):
    doc, binary = read_glb(path)
    result = {}
    for ni, pi, p, t, material in mesh_instances(doc, binary):
        mat = doc['materials'][material]
        if mat.get('pbrMetallicRoughness', {}).get('baseColorTexture'):
            continue
        key = doc['nodes'][ni]['name'], mat['name']
        assert key not in result
        result[key] = p, t
    return result


def against_source(original, path):
    candidate = parts(path)
    assert original.keys() == candidate.keys(), 'source mesh membership changed'
    maximum = 0
    worst = None
    for key, (p, t) in original.items():
        q, u = candidate[key]
        check = deviation(p, t, q, u, count=4096)
        if check['max'] > maximum:
            maximum, worst = check['max'], key
    return {'max_source_sampled_deviation_mm': maximum * 1000, 'worst_node_material': worst,
            'sampling': '4096 triangles per direction, per node/material group'}


def run(name):
    root = Path('out/recursive-simplification') / name
    root.mkdir(parents=True, exist_ok=False)
    installed = Path('../rm-simulator/local-assets/field')
    current = installed / ('equipment/base.glb' if name == 'base' else 'resource-zone.glb')
    source = root / 'source.glb'
    if name == 'base':
        d, b = read_glb(Path('out/tolerance-source/equipment/base.glb'))
        d, b, _ = strip(d, b, [{'node': 'source_13267588_001_1_1', 'material': 'colour_1.0000,1.0000,1.0000'}])
        write_glb(source, d, b)
    else:
        shutil.copy2('out/resource-refinement-source-visual.glb', source)
    original = parts(source)
    preserve = [{'node': 'source_13267852_7000001_1_6', 'primitive': 0}] if name != 'base' else []
    results = []
    baseline = root / 'current.glb'; shutil.copy2(current, baseline)
    results.append(dict(name='current', triangles=scene_triangles(read_glb(baseline)[0]), **against_source(original, baseline)))
    print(name, results[-1], flush=True)
    # Repeated same-tolerance passes start from the current installed mesh.
    previous = baseline
    for iteration in range(1, 4):
        path = root / f'recursive-{iteration}.glb'; shutil.copy2(previous, path)
        start = time.time()
        stats = simplify_glb(path, 4, sampled_limit_mm=12, deviation_samples=4096, lock_borders=False, preserve=preserve)
        check = against_source(original, path)
        results.append(dict(name=f'recursive-{iteration}', triangles=stats['after_triangles'],
                            local_deviation_mm=stats['max_sampled_deviation_mm'], seconds=time.time()-start, **check))
        print(name, results[-1], flush=True)
        previous = path
        if results[-2]['triangles']-results[-1]['triangles'] < results[-2]['triangles']*.005:
            break
    # Higher-error candidates always restart from the unsimplified source.
    for error in (6, 8):
        path = root / f'direct-{error}mm.glb'; shutil.copy2(source, path)
        start = time.time()
        stats = simplify_glb(path, error, sampled_limit_mm=error*3, deviation_samples=4096, lock_borders=False, preserve=preserve)
        if name == 'base':
            atlas = json.loads((installed / 'equipment/texture-atlas.json').read_text())['files']['base.glb']
            pages = [(installed / 'equipment' / page['file']).read_bytes() for page in atlas['pages']]
            d, b = read_glb(path); d, b = attach(d, b, pages, atlas['patches'], .0005); write_glb(path, d, b)
        results.append(dict(name=f'direct-{error}mm', triangles=scene_triangles(read_glb(path)[0]),
                            local_deviation_mm=stats['max_sampled_deviation_mm'], seconds=time.time()-start,
                            **against_source(original, path)))
        print(name, results[-1], flush=True)
    report = {'asset': name, 'source_sha256': digest(source), 'current_sha256': digest(current), 'results': results}
    (root / 'comparison.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('asset', choices=['resource-zone', 'base'])
    run(parser.parse_args().asset)
