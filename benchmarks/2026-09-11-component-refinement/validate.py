# SPDX-License-Identifier: MIT OR Apache-2.0
"""Verify source component survival and report actual placed triangle reductions."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import accessor, read_glb, scene_nodes
from collision_artwork import strip


def primitives(doc, binary):
    out = {}
    for ni, _, _ in scene_nodes(doc):
        node = doc['nodes'][ni]
        if 'mesh' not in node:
            continue
        for p in doc['meshes'][node['mesh']]['primitives']:
            key = node['name'], doc['materials'][p['material']]['name']
            assert key not in out
            points = accessor(doc, binary, p['attributes']['POSITION']).astype('f4')
            triangles = (accessor(doc, binary, p['indices']) if 'indices' in p else np.arange(len(points))).reshape(-1, 3)
            out[key] = points, triangles
    return out


def components(source, candidate):
    before = primitives(*source); after = primitives(*candidate)
    total = 0
    dtype = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4')])
    for key, (p, t) in before.items():
        assert key in after, key
        q, u = after[key]
        p, inv = np.unique(p, axis=0, return_inverse=True)
        t = inv[t]
        edges = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
        _, labels = connected_components(coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(p), len(p))), directed=False)
        # Simplifier selects existing positions; no quantized or moved vertices.
        lookup = np.ascontiguousarray(p).view(dtype).ravel()
        wanted = np.ascontiguousarray(q).view(dtype).ravel()
        indices = np.searchsorted(lookup, wanted)
        assert (indices < len(p)).all(), key
        np.testing.assert_array_equal(p[indices], q, err_msg=str(key))
        original = np.unique(labels[t.ravel()]); remaining = np.unique(labels[indices[u.ravel()]])
        np.testing.assert_array_equal(original, remaining, err_msg=str(key))
        face_labels = labels[indices[u]]
        assert (face_labels == face_labels[:, :1]).all(), 'triangle spans disconnected components'
        total += len(original)
    return {'source_components': total, 'missing_components': 0, 'new_vertex_positions': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, default=Path('out/resource-reference-candidate'))
    parser.add_argument('--after', type=Path, default=Path('out/component-refinement-candidate'))
    parser.add_argument('--source', type=Path, default=Path('out/tolerance-source'))
    args = parser.parse_args()
    current, candidate, source = args.before, args.after, args.source
    report = {}
    for scope, name in [('', 'resource-zone'), ('equipment', 'base')]:
        old = json.loads((current / scope / 'manifest.json').read_text())['assets'][name]
        new = json.loads((candidate / scope / 'manifest.json').read_text())['assets'][name]
        item = {}
        for kind in ('visual', 'collision'):
            count = 'triangles' if kind == 'visual' else 'collision_triangles'
            if name == 'resource-zone':
                raw = read_glb(Path('out') / ('resource-refinement-source-' + kind + '.glb'))
            else:
                raw = read_glb(source / scope / old[kind])
                d, b, _ = strip(*raw, [{'node': 'source_13267588_001_1_1', 'material': 'colour_1.0000,1.0000,1.0000'}])
                raw = d, b
            check = components(raw, read_glb(candidate / scope / new[kind]))
            item[kind] = dict(before=old[count], after=new[count], removed=old[count]-new[count],
                              reduction_percent=100*(old[count]-new[count])/old[count],
                              sampled_limit_mm=new['mesh_simplification'][kind]['sampled_deviation_limit_mm'],
                              max_sampled_deviation_mm=new['mesh_simplification'][kind]['max_sampled_deviation_mm'], **check)
        report[name] = item
    report['placed_removed'] = {kind: 2*sum(report[n][kind]['removed'] for n in ('resource-zone', 'base')) for kind in ('visual', 'collision')}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
