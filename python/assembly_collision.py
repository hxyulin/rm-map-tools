# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Reproducible link-local collision shapes for the assembly workbench.

Static housings and jaws keep their triangles/apertures. Other source leaves
use individual convex hulls (never a hull across a whole articulated arm).
"""
import hashlib
import json
import numpy as np
from scipy.spatial import ConvexHull, QhullError
from gltf_scene import read_glb, mesh_instances, scene_nodes
C = np.array([[0., 0, 1], [1, 0, 0], [0, 1, 0]])


def hull_or_mesh(points, triangles):
    """Return a convex source-leaf envelope, or exact triangles for planar leaves."""
    points, inverse = np.unique(points, axis=0, return_inverse=True)
    triangles = inverse[triangles]
    try:
        hull = ConvexHull(points)
        return dict(kind='convex', points_m=points[hull.vertices].tolist())
    except QhullError:
        return dict(kind='mesh', points_m=points.tolist(), triangles=triangles.tolist())


def link_local_points(points, native_frame):
    """Convert world-native glTF points into one link's local FLU frame."""
    return ((points - native_frame[:3, 3]) @ native_frame[:3, :3]) @ C.T


def export(root):
    """Export named shapes in the same FLU link frames as the source rig."""
    bodies, meshes, sources, counts = {}, {}, {}, {}
    for file in ['engineer.glb', 'core-base.glb', 'core-arm.glb', 'core-head.glb', 'unit.glb']:
        path = root / file
        sources[file] = hashlib.sha256(path.read_bytes()).hexdigest()
        document, binary = read_glb(path)
        frames = {document['nodes'][i]['name'][5:]: m for i, m, _ in scene_nodes(document)
                  if document['nodes'][i].get('name', '').startswith('link/')}
        for ni, _, p, t, _ in mesh_instances(document, binary):
            name = document['nodes'][ni]['extras']['assembly_group']
            frame = frames[name]
            local = link_local_points(p, frame)
            counts[name] = counts.get(name, 0) + 1
            if name.startswith('engineer/') or name in {'unit/unit', 'core/q', 'core/p'} or (file == 'core-head.glb' and name == 'core/j6'):
                meshes.setdefault(name, []).append((local, t))
            else:
                bodies.setdefault(name, []).append(hull_or_mesh(local, t))
    for name, parts in meshes.items():
        # Keep leaf boundaries so the runtime can build conservative hull
        # envelopes for broad-phase rejection, then query the exact surfaces.
        for p, t in parts:
            unique, inverse = np.unique(p, axis=0, return_inverse=True)
            bodies.setdefault(name, []).append(dict(kind='mesh', points_m=unique.tolist(), triangles=inverse[t].tolist()))
    excluded = []
    for prefix in ['engineer', 'core']:
        links = [f'{prefix}/body'] + [f'{prefix}/j{i}' for i in range(1, 7)]
        excluded += [[a, b] for a, b in zip(links, links[1:])]
    excluded += [['engineer/j6', f'engineer/{jaw}'] for jaw in ['jaw-left', 'jaw-right']]
    excluded += [['engineer/camera-lift','engineer/uwb']]
    excluded += [['engineer/j3','engineer/camera-lift'],['engineer/j3','engineer/uwb']]
    excluded += [['engineer/j4','engineer/j6'],['engineer/jaw-left','engineer/jaw-right']]
    excluded += [['core/j6', 'core/p'], ['core/j6', 'core/q'], ['core/p', 'core/q']]
    # Floor is a finite block in the inspection fixture, with top at z=0.
    bodies['floor'] = [dict(kind='box', half_m=[4., 4., .05])]
    result = dict(schema=1, source_glbs=sources, bodies=[dict(frame=k, parts=v) for k, v in sorted(bodies.items())],
                  excluded_pairs=excluded, source_leaves=counts,
                  policy='Exact Engineer/unit/housing triangles; individual Core positioning-arm convex source leaves. Joint neighbours and guided Core carriage interfaces are exempt. Grasp/unit-post exceptions are runtime-state dependent. No force dynamics.')
    path = root / 'collision.json'; path.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False)+'\n')
    return dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
