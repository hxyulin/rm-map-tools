#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check bound Hero source coverage, rest geometry and counter-rotating linkage."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, mesh_instances, scene_nodes
from bind_hero import PIVOT, TIP, rotation, group


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.package / 'manifest.json').read_text())
    name = manifest['source']['source_model_id']
    source_path = args.prepared / (name + '-pilot') / 'low.glb'
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == manifest['prepared_visual_sha256']
    sd, sb = read_glb(source_path)
    center = np.asarray(json.loads((args.prepared / (name + '-frame.json')).read_text())['source_center_mm']) / 1000
    r = np.asarray(manifest['source']['review_rotation'])
    source = {sd['nodes'][ni]['name'] + f'-{pi}': (p[t], sd['materials'][m])
              for ni, pi, p, t, m in mesh_instances(sd, sb)}
    nd, nb = read_glb(args.package / 'neutral.glb')
    seen = set();maximum_error = 0.;shell_groups = set()
    floor = float(manifest['link_origins_gltf_m']['yaw'][1]) - .076
    for ni, pi, p, t, m in mesh_instances(nd, nb):
        node = nd['nodes'][ni];key = node['name'];extra = node['extras']
        assert key not in seen;seen.add(key)
        expected, material = source[key]
        assert nd['materials'][m] == material
        expected = (expected + center) @ r.T + [0, floor, 0]
        assert expected.shape == p[t].shape
        error = float(np.abs(expected-p[t]).max());maximum_error = max(maximum_error,error)
        assert error < 2e-7,(key,error)
        assert extra['source_occurrence_path'] and group(extra['source_occurrence_path']) == extra['motion_group']
        assert extra['articulation_bound']
        if extra['native_solid_index'] == 0:shell_groups.add(extra['source_occurrence_path'])
    assert seen == source.keys()
    assert len(shell_groups) == 4,shell_groups
    for name, spec in manifest['poses'].items():
        document, data = read_glb(args.package / (name + '.glb'))
        poses = {index:matrix for index,matrix,parent in scene_nodes(document)}
        nodes = {n['name']:i for i,n in enumerate(document['nodes']) if n.get('name','').startswith('link/')}
        angle = np.deg2rad(spec['angle_deg'])
        expected = PIVOT + rotation(angle) @ (TIP-PIVOT)
        assert np.allclose(poses[nodes['link/pitch']][:3,3], expected,atol=1e-10)
        assert np.allclose(poses[nodes['link/pitch']][:3,:3],np.eye(3),atol=1e-12)
        assert sum(len(t) for ni,pi,p,t,m in mesh_instances(document,data)) == spec['triangles']
    report = {'retained_parts':len(seen),'open_shell_leaf_groups':len(shell_groups),
              'max_rest_vertex_error_m':maximum_error,'source_materials_preserved':True,
              'counter_rotation_and_hinge_closure':True}
    (args.package / 'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':main()
