"""Verify unchanged visuals and exact collider removal against a source package."""
import json
import sys
from pathlib import Path
import numpy as np
from collections import Counter
from gltf_scene import read_glb, mesh_instances
from deploy_field import digest
from simplify_package import check_bindings

source, candidate = map(Path, sys.argv[1:])
report = json.loads((candidate/'decoration-layer.json').read_text())
manifest = json.loads((candidate/'manifest.json').read_text())
assert report['source_manifest_sha256'] == digest(source/'manifest.json')

def parts(path):
    doc, binary = read_glb(path)
    return {(doc['nodes'][ni]['name'], doc['materials'][m]['name']): (p, t)
            for ni, _, p, t, m in mesh_instances(doc, binary)}

def triangle_set(parts):
    return Counter(tuple(sorted(tuple(v) for v in tri))
                   for p, t in parts.values() for tri in p[t])

for name, record in report['assets'].items():
    entry = manifest['assets'][name]
    for kind in ('visual', 'collision'):
        assert digest(candidate/entry[kind]) == entry[kind+'_sha256']
        old, new = parts(source/entry[kind]), parts(candidate/entry[kind])
        removed = {(s['node'], s['material']) for s in record['removed']} if kind == 'collision' else set()
        if record.get('backing_repair'):
            if kind == 'visual':
                assert triangle_set(old) == triangle_set(new)
            else:
                node = 'source_13267333_0006_1_1'
                old = {key: value for key, value in old.items() if key not in removed}
                gray = (node, 'colour_0.6275,0.6275,0.6275')
                dark = (node, 'colour_0.2000,0.2000,0.2000')
                p, t = old[gray]
                mask = np.ones(len(t), bool)
                mask[137:281] = False
                mask[287:431] = False
                old[gray] = p, t[mask]
                p, t = old[dark]
                top = np.max(abs(p[t, 2]-.4), axis=1) < 1e-6
                old[dark] = p, t[~top]
                p, t = new[dark]
                top = np.max(abs(p[t, 2]-.4), axis=1) < 1e-6
                assert int(top.sum()) == 16
                # No symbol vertices survive in the restored deck triangulation.
                for sign in [-1, 1]:
                    centre = np.array([1.2763055*sign, -.8448808*sign])
                    assert np.linalg.norm(p[t[top]][:, :, :2]-centre, axis=2).min() > .09
                new[dark] = p, t[~top]
                assert triangle_set(old) == triangle_set(new)
            continue
        assert set(old) - set(new) == removed
        assert set(new) == set(old) - removed
        for key in new:
            for a, b in zip(old[key], new[key]):
                np.testing.assert_array_equal(a, b)
    print(name, 'visuals identical; collider removal and backing checks passed')
if manifest.get('articulation'):
    art = manifest['articulation']
    assert digest(candidate/art['file']) == art['sha256']
    sidecar = json.loads((candidate/art['file']).read_text())
    for name, asset in sidecar['assets'].items():
        for kind, binding in asset.get('files', {}).items():
            path = candidate/manifest['assets'][name][kind]
            assert digest(path) == binding['sha256']
            doc, _ = read_glb(path)
            check_bindings(doc, binding)
print('Checksums and semantic bindings valid')
