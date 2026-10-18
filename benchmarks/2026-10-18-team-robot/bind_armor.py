#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Replace source armor surfaces in an existing, verified Omni/Hero motion package."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, write_glb, mesh_instances
from robot_armor import identify_armor, strip_armor_surfaces, verify_armor_replacement
from robot_materials import apply_materials, verify_materials


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.package.resolve() == a.out.resolve():
        p.error('keep the original source motion package intact')
    manifest = json.loads((a.package / 'manifest.json').read_text())
    hero = manifest.get('profile') == 'artisans-folding-hero-v1'
    # Pin both original source IDs for the assembled model.
    if hero:
        assert manifest['source']['cad_sha256'] == '71d6ddb07672028613c03ab2abca508cd616f93a3e2b5481b6696a063b86dd6e'
    else:
        assert manifest['sources']['chassis']['cad_sha256'] == 'b5a603acd8222295096184b68824eacf7302c7955e67943568dbc702a0611357'
        assert manifest['sources']['gimbal']['cad_sha256'] == '47e6aab908c3fbb443b9f3d950e77144ea2bc7baf6e6aa9d8a754174e822ed7f'
    rows = json.loads((a.sources / 'artisans-2026-tunnel-hero-hierarchy.json').read_text()) if hero else []
    neutral, binary = read_glb(a.package / 'neutral.glb')
    report = identify_armor(neutral, binary, rows, zhulong=not hero)
    if len(report['modules']) != 4:
        raise ValueError('expected exactly four physical armor mounts')
    # Convert a GLB world frame to the same FLU body frame used by physics.
    convert = np.array([[0,0,1], [1,0,0], [0,1,0]])
    body_y = manifest['body_origin_y_m'] if hero else .175675827304379
    for m in report['modules']:
        matrix = np.array(m['face_matrix_gltf']).reshape(4,4,order='F')
        basis = convert @ matrix[:3,:3]
        center = convert @ (matrix[:3,3] - [0,body_y,0])
        q = Rotation.from_matrix(basis).as_quat()
        m['body_face_pose_flu'] = {'translation_m': center.tolist(), 'rotation_wxyz': q[[3,0,1,2]].tolist()}
        m['id'] = int(np.round(np.arctan2(basis[1,0], basis[0,0]) / (np.pi/2))) % 4
    report['modules'].sort(key=lambda m:m['id'])
    assert [m['id'] for m in report['modules']] == list(range(4))
    report['runtime_replacement'] = True
    report['producer_sha256'] = digest(Path(__file__))
    report['pass_sha256'] = digest(ROOT / 'python/robot_armor.py')
    report['input_neutral_sha256'] = digest(a.package / 'neutral.glb')
    a.out.mkdir(parents=True, exist_ok=True)
    for name, spec in manifest['files'].items():
        path = a.package / spec['file']
        if digest(path) != spec['sha256']:
            raise ValueError('source motion package checksum mismatch')
        d, b = read_glb(path)
        # Material assignments retain exact geometry before surface substitution.
        appearance = copy.deepcopy(d)
        # Bound packages carry singular source paths instead of candidate aliases.
        for node in appearance['nodes']:
            e = node.get('extras', {})
            if 'source_occurrence_path' in e:
                e['source_occurrence_paths'] = [e['source_occurrence_path']]
        # Preserve the source pose/hierarchy; appearance provenance additions are
        # independent of the geometry/material preservation validator.
        d = copy.deepcopy(appearance)
        styled_binary, materials = apply_materials(appearance, b, rows)
        materials['validation'] = verify_materials(d, b, appearance, styled_binary)
        original_surfaces = copy.deepcopy(appearance)
        strip_armor_surfaces(appearance, report)
        report['validation'] = verify_armor_replacement(original_surfaces, appearance, report)
        appearance['asset'].setdefault('extras', {})['armor_bindings'] = report
        write_glb(a.out / spec['file'], appearance, styled_binary)
        spec['sha256'] = digest(a.out / spec['file'])
        if name == 'neutral':
            report['retained_visual_triangles'] = sum(len(t) for _,_,_,t,_ in mesh_instances(appearance,styled_binary))
    manifest['armor'] = report
    manifest['files']['neutral']['sha256'] = digest(a.out / 'neutral.glb')
    (a.out / 'armor.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (a.out / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (a.out / 'CAD-NOTICE.md').write_text((a.package/'CAD-NOTICE.md').read_text()+'\nSource armor front/shell/diffuser surfaces replaced by simulator modules. Original mounts/hardware retained; inferred display materials and physical fit are not source-authored colors or referee certification.\n')
    print(json.dumps({'modules': len(report['modules']), 'retained_visual_triangles': report['retained_visual_triangles']}))


if __name__ == '__main__':
    main()
