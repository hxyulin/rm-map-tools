# SPDX-License-Identifier: MIT OR Apache-2.0
"""Experiment: accept repeated simplification per mesh only within source limits."""
import copy
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
import numpy as np
from gltf_scene import accessor, read_glb, write_glb, scene_nodes, mesh_instances
from simplify_package import simplify_glb, append_accessor, compact, scene_triangles, digest
from mesh_quality import deviation
from compare import parts, against_source


def guard(previous, candidate, original, limit):
    old_doc, old_bin = read_glb(previous)
    doc, binary = read_glb(candidate)
    assert old_doc['materials'] == doc['materials']
    old_parts = parts(previous)
    grouped = {}
    for ni, pi, p, t, material in mesh_instances(doc, binary):
        key = doc['nodes'][ni]['name'], doc['materials'][material]['name']
        if key not in original:
            continue  # Unchanged native texture quad.
        mesh = doc['nodes'][ni]['mesh']
        source_p, source_t = original[key]
        before_p, before_t = old_parts[key]
        if len(t) >= len(before_t):
            accept = False
        else:
            error = deviation(source_p, source_t, p, t, count=4096)['max']*1000
            accept = error <= limit
        grouped.setdefault((mesh, pi), []).append((accept, ni))
    payload = bytearray(binary)
    kept = rejected = 0
    for (mi, pi), decisions in grouped.items():
        if all(a for a, _ in decisions):
            kept += 1
            continue
        rejected += 1
        ni = decisions[0][1]
        p = copy.deepcopy(old_doc['meshes'][old_doc['nodes'][ni]['mesh']]['primitives'][pi])
        for semantic, index in p['attributes'].copy().items():
            a = old_doc['accessors'][index]
            ai = append_accessor(doc, payload, accessor(old_doc, old_bin, index).copy(), a['type'], a['componentType'])
            if 'normalized' in a:
                doc['accessors'][ai]['normalized'] = a['normalized']
            p['attributes'][semantic] = ai
        if 'indices' in p:
            index = p['indices']; a = old_doc['accessors'][index]
            p['indices'] = append_accessor(doc, payload, accessor(old_doc, old_bin, index).copy(), a['type'], a['componentType'])
        doc['meshes'][mi]['primitives'][pi] = p
    binary = compact(doc, bytes(payload))
    # Ordinary single-pass metrics no longer describe this composed candidate.
    doc['asset'].get('extras', {}).pop('mesh_simplification', None)
    doc['asset'].setdefault('extras', {})['recursive_source_guard'] = {
        'source_sampled_limit_mm': limit, 'previous_sha256': digest(previous),
        'sampling_triangles_per_direction': 4096}
    write_glb(candidate, doc, binary)
    return kept, rejected


def run(name, limit=12):
    root = Path('out/recursive-simplification') / name
    original = parts(root / 'source.glb')
    previous = root / 'current.glb'
    preserve = [{'node': 'source_13267852_7000001_1_6', 'primitive': 0}] if name == 'resource-zone' else []
    results = []
    for iteration in range(1, 4):
        tag = 'guarded' if limit == 12 else f'guarded-{limit:g}mm'
        path = root / f'{tag}-{iteration}.glb'; shutil.copy2(previous, path)
        simplify_glb(path, 4, sampled_limit_mm=12, deviation_samples=4096, lock_borders=False, preserve=preserve)
        accepted, rejected = guard(previous, path, original, limit)
        check = against_source(original, path)
        assert check['max_source_sampled_deviation_mm'] <= limit
        item = dict(name=f'{tag}-{iteration}', triangles=scene_triangles(read_glb(path)[0]),
                    accepted_groups=accepted, retained_previous_groups=rejected, **check)
        results.append(item); print(name, item, flush=True)
        if scene_triangles(read_glb(previous)[0])-item['triangles'] < item['triangles']*.005:
            break
        previous = path
    (root / (tag + '.json')).write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    run(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 12)
