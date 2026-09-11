# SPDX-License-Identifier: MIT OR Apache-2.0
"""Audit whole source components within the previously inspected unit envelopes.

This is a benchmark selection generator, not a heuristic in the exporter. Output
is an explicit triangle-range list that must accompany a source checksum.
"""
import json
from pathlib import Path
import sys
from collections import defaultdict
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'python'))
from gltf_scene import read_glb, mesh_instances


def select(path):
    doc, binary = read_glb(path)
    selections = [defaultdict(list) for _ in range(6)]
    for ni, pi, points, triangles, _ in mesh_instances(doc, binary):
        name = doc['nodes'][ni]['name']
        if name == 'source_13267862_7000001_1_16' and pi in (0, 6):
            continue  # Hub sockets and inserted shafts stay fixed.
        _, inverse = np.unique(np.round(points, 6), axis=0, return_inverse=True)
        welded = inverse[triangles]
        edges = np.concatenate([welded[:, [0, 1]], welded[:, [1, 2]], welded[:, [2, 0]]])
        size = int(inverse.max() + 1)
        _, labels = connected_components(coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(size, size)), directed=False)
        face_labels = labels[welded[:, 0]]
        for component in np.unique(face_labels):
            indices = np.flatnonzero(face_labels == component)
            xyz = points[triangles[indices]].reshape(-1, 3)
            if xyz[:, 0].min() < -1.093 or xyz[:, 0].max() > -.997:
                continue
            for unit in range(6):
                angle = unit * np.pi / 3
                radial = xyz[:, 1] * np.sin(angle) + (xyz[:, 2] - .6999) * np.cos(angle)
                tangent = xyz[:, 1] * np.cos(angle) - (xyz[:, 2] - .6999) * np.sin(angle)
                if radial.min() >= .0748 and radial.max() <= .2252 and abs(tangent).max() <= .048:
                    selections[unit][name, pi].extend(indices.tolist())
                    break
    entities = []
    for unit, parts in enumerate(selections):
        assert parts, 'unit envelope selected no source components'
        entity = {'id': f'energy-unit-{unit + 1}',
                  'origin_m': [-1.045, float(.15 * np.sin(unit * np.pi / 3)), float(.6999 + .15 * np.cos(unit * np.pi / 3))], 'parts': []}
        for (name, pi), indices in parts.items():
            values = np.sort(indices)
            runs = np.split(values, np.where(np.diff(values) > 1)[0] + 1)
            entity['parts'].append({'node': name, 'primitive': pi, 'triangle_ranges': [[int(r[0]), int(r[-1] + 1)] for r in runs]})
        entities.append(entity)
    return entities


if __name__ == '__main__':
    print(json.dumps(select(Path(sys.argv[1])), indent=2))
