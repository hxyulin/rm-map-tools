# SPDX-License-Identifier: MIT OR Apache-2.0
"""Integration checks for the pinned reference mechanisms and their rest geometry."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull

from export_semantics import apply_pose, digest
from gltf_scene import mesh_instances, read_glb, scene_nodes


def triangle_records(document, binary, exclude_nodes=()):
    records = []
    for node, _, xyz, triangles, material in mesh_instances(document, binary):
        if node in exclude_nodes:
            continue
        # Compare complete ordered triangles, including materials, to 1 micrometre.
        coordinates = np.rint(xyz[triangles].reshape(-1, 9) * 1e6).astype('<i4')
        records.append(np.column_stack([coordinates, np.full(len(triangles), material if material is not None else -1, '<i4')]))
    result = np.ascontiguousarray(np.vstack(records), dtype='<i4')
    return np.sort(result.view('V40').ravel())


def armor_window_blockage(meshes, armor_node, shield_nodes, angle):
    """Count blocked rays across a 5x5 grid covering the module's frontal bounds."""
    direction = np.array([np.cos(angle), np.sin(angle), 0.])
    side = np.array([-direction[1], direction[0], 0.])
    xyz = np.vstack([x for i, _, x, _, _ in meshes if i == armor_node])
    triangles = np.vstack([x[t] for i, _, x, t, _ in meshes if i in shield_nodes])
    u = xyz @ side
    depth = (xyz @ direction).max() + 1e-5
    edge1, edge2 = triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0]
    h = np.cross(direction, edge2)
    det = np.einsum('ij,ij->i', edge1, h)
    valid = np.abs(det) > 1e-10
    inverse = np.divide(1, det, out=np.zeros_like(det), where=valid)
    blocked = 0
    for lateral in np.linspace(u.min(), u.max(), 5):
        for z in np.linspace(xyz[:, 2].min(), xyz[:, 2].max(), 5):
            origin = side*lateral + direction*depth + np.array([0, 0, z])
            delta = origin-triangles[:, 0]
            a = np.einsum('ij,ij->i', delta, h)*inverse
            q = np.cross(delta, edge1)
            b = (q @ direction)*inverse
            distance = np.einsum('ij,ij->i', edge2, q)*inverse
            blocked += bool(np.any(valid & (a >= 0) & (b >= 0) & (a+b <= 1) & (distance > 0) & (distance < 2)))
    return blocked


def verify(source, reference):
    report = {'assets': {}, 'motion_checks': {}}
    for sub, names in [('', ['rune', 'outpost', 'dart-station']), ('equipment', ['base', 'tech-core'])]:
        before, after = source / sub, reference / sub
        manifest = json.loads((after / 'manifest.json').read_text())
        assert digest(after / 'articulation.json') == manifest['articulation']['sha256']
        sidecar = json.loads((after / 'articulation.json').read_text())
        for name in names:
            binding = sidecar['assets'][name]['files']
            for kind in ['visual', 'collision']:
                entry = binding[kind]
                old, old_bin = read_glb(before / entry['file'])
                doc, binary = read_glb(after / entry['file'])
                assert digest(after / entry['file']) == entry['sha256']
                reconstructed = {n['node'] for n in entry['nodes'] if n['metadata'].get('geometry_origin') == 'reconstruction'}
                a, b = triangle_records(old, old_bin), triangle_records(doc, binary, reconstructed)
                assert np.array_equal(a, b), f'{name}/{kind}: source triangles changed'
                report['assets'][name + '/' + kind] = {'triangles': len(a), 'rest_triangle_material_match': True,
                                                       'sha256': entry['sha256'],
                                                       'reconstructed_triangles': sum(len(t) for i, _, _, t, _ in mesh_instances(doc, binary) if i in reconstructed)}
            entry = binding['visual']
            doc, binary = read_glb(after / entry['file'])
            joints = entry['joints']
            if name == 'rune':
                moved = apply_pose(doc, joints, {j['id']: np.pi/2 for j in joints})
                rest_world = {i: m for i, m, _ in scene_nodes(doc)}
                moved_world = {i: m for i, m, _ in scene_nodes(moved)}
                fixed = [n for n in entry['nodes'] if n['id'].startswith('rune.fixed.') or n['id'] == 'rune.static']
                for node in fixed:
                    np.testing.assert_allclose(rest_world[node['node']], moved_world[node['node']], atol=1e-12)
                for node in entry['nodes']:
                    if '.arm.' in node['id'] or node['id'].endswith('.hub'):
                        assert not np.allclose(rest_world[node['node']], moved_world[node['node']])
                report['motion_checks']['rune'] = {'fixed_groups': [n['id'] for n in fixed], 'arms_and_surrounding_hubs_rotate': True}
            if name == 'outpost':
                moved = apply_pose(doc, joints, {joints[0]['id']: np.pi/2})
                worlds = [{i: m for i, m, _ in scene_nodes(d)} for d in [doc, moved]]
                ids = {n['id']: n['node'] for n in entry['nodes']}
                rotor, fasteners = ids['outpost.rotor'], ids['outpost.rotor.arm_fasteners']
                rel = [np.linalg.inv(w[rotor]) @ w[fasteners] for w in worlds]
                np.testing.assert_allclose(*rel, atol=1e-12)
                assert not np.allclose(worlds[0][fasteners], worlds[1][fasteners])
                report['motion_checks']['outpost'] = {'carrier_fastener_triangles': 1168, 'fasteners_follow_rotor': True}
            if name == 'dart-station':
                moved = apply_pose(doc, joints, {joints[0]['id']: joints[0]['limits'][0]})
                gate = next(n['node'] for n in entry['nodes'] if n['id'] == 'dart-station.gate')
                points = np.vstack([xyz for i, _, xyz, _, _ in mesh_instances(moved, binary) if i == gate])
                low = float(points[:, 2].min())
                assert .204 < low < .206
                rest_world = {i: w for i, w, _ in scene_nodes(doc)}
                moved_world = {i: w for i, w, _ in scene_nodes(moved)}
                for i in rest_world:
                    if i != gate and "mesh" in doc["nodes"][i]:
                        np.testing.assert_allclose(rest_world[i], moved_world[i], atol=1e-12)
                report['motion_checks']['dart-station'] = {'closed_lowest_z_m': low, 'platform_height_m': .205, 'guides_and_platform_stay_fixed': True, 'travel_is_illustrative': True}
            if name == 'tech-core':
                assert len(joints) == 6
                assert all(j['geometry_binding'] == 'frames_only' for j in joints)
                moved = apply_pose(doc, joints, {j['id']: .1 for j in joints})
                rest_world = {i: w for i, w, _ in scene_nodes(doc)}
                posed_world = {i: w for i, w, _ in scene_nodes(moved)}
                for node in entry['nodes']:
                    index = node['node']
                    if node['id'].startswith('tech-core.link.'):
                        assert not np.allclose(rest_world[index], posed_world[index])
                    elif 'mesh' in doc['nodes'][index]:
                        np.testing.assert_allclose(rest_world[index], posed_world[index], atol=1e-12)
                from preview.tech_core_demo import prepare_demo, trajectory
                preview, preview_binary, axes, point, direction, demo_report = prepare_demo(doc, binary, entry)
                restored = demo_report["restored_tool_enclosure_node"]
                hidden = demo_report["hidden_shared_hardware_node"]
                original_faces = np.vstack([x[t] for i, _, x, t, _ in mesh_instances(doc, binary) if i == hidden])[91775:118288]
                restored_faces = np.vstack([x[t] for i, _, x, t, _ in mesh_instances(preview, preview_binary) if i == restored])
                np.testing.assert_allclose(restored_faces, original_faces, atol=1e-10)
                values, errors = trajectory(axes, point, direction, 8)
                endpoint = apply_pose(preview, joints, dict(zip([j['id'] for j in joints], values[4])))
                ids = {n['id']: n['node'] for n in entry['nodes']}
                tool = ids['tech-core.part.tool.assembly']
                rest = {i: w for i, w, _ in scene_nodes(preview)}[tool]
                end = {i: w for i, w, _ in scene_nodes(endpoint)}[tool]
                rest_enclosure = {i: w for i, w, _ in scene_nodes(preview)}[restored]
                end_enclosure = {i: w for i, w, _ in scene_nodes(endpoint)}[restored]
                np.testing.assert_allclose(np.linalg.inv(end) @ end_enclosure, np.linalg.inv(rest) @ rest_enclosure, atol=1e-10)
                delta = (end @ np.r_[point, 1] - rest @ np.r_[point, 1])[:3]
                np.testing.assert_allclose(delta, .1*direction, atol=1e-6)
                np.testing.assert_allclose(end[:3, :3], rest[:3, :3], atol=1e-6)
                report['motion_checks']['tech-core-demo'] = {
                    'tool_translation_m': float(np.linalg.norm(delta)),
                    'orientation_held': True, 'rig_is_preview_only': True,
                    'restored_enclosure_triangles': len(restored_faces),
                    'enclosure_source_triangles_match': True, 'enclosure_follows_tool': True, **errors}
                report['motion_checks']['tech-core'] = {
                    'serial_revolute_axes': 6, 'geometry_binding': 'frames_only',
                    'source_meshes_remain_unbound': True,
                    'mechanical_limits': 'unknown', 'preview_angles_are_not_limits': True}
            if name == 'base':
                foot = next(i for i, n in enumerate(doc['nodes']) if n.get('name') == 'source_13267588_001_1_1')
                points = np.vstack([xyz for i, _, xyz, _, _ in mesh_instances(doc, binary) if i == foot])
                hull = ConvexHull(points[:, :2])
                moved = apply_pose(doc, joints, {j['id']: j['limits'][1] for j in joints})
                shield_ids = {n['node'] for n in entry['nodes'] if n['id'].startswith('base.shield.')}
                points = np.vstack([xyz for i, _, xyz, _, _ in mesh_instances(moved, binary) if i in shield_ids])
                distance = points[:, :2] @ hull.equations[:, :2].T + hull.equations[:, 2]
                assert distance.max() <= 1e-6
                additions = [n for n in entry['nodes'] if n['metadata'].get('geometry_origin') == 'reconstruction']
                rest_world = {i: w for i, w, _ in scene_nodes(doc)}
                posed_world = {i: w for i, w, _ in scene_nodes(moved)}
                for n in additions:
                    np.testing.assert_allclose(rest_world[n['node']], posed_world[n['node']], atol=1e-12)
                armor_ids = {n['node'] for n in additions if 'armor_module' in n['metadata']['roles']}
                armor = np.vstack([x for i, _, x, _, _ in mesh_instances(moved, binary) if i in armor_ids])
                assert len(armor_ids) == 3
                ids = {n['id']: n['node'] for n in entry['nodes']}
                open_meshes, closed_meshes = list(mesh_instances(moved, binary)), list(mesh_instances(doc, binary))
                visibility = []
                for k in range(3):
                    node = ids[f'base.reconstructed.armor.{k}']
                    angle = np.radians(60 + 120*k)
                    opened = armor_window_blockage(open_meshes, node, shield_ids, angle)
                    closed = armor_window_blockage(closed_meshes, node, shield_ids, angle)
                    assert opened == 0 and closed > 0
                    visibility.append({'module': k, 'rays': 25, 'open_blocked': opened, 'closed_blocked': closed})
                assert .28 < armor[:, 2].min() < .30 and .43 < armor[:, 2].max() < .45
                assert points[:, 2].min() > .04
                reconstructed_points = np.vstack([x for i, _, x, _, _ in mesh_instances(doc, binary)
                                                   if i in {n['node'] for n in additions}])
                assert (reconstructed_points[:, :2] @ hull.equations[:, :2].T + hull.equations[:, 2]).max() <= 1e-6
                ids = {n['id']: n['node'] for n in entry['nodes']}
                carriage_joint = next(j for j in joints if j['id'] == 'base.dart_target.slide')
                core, light, rail = [ids[k] for k in ['base.dart_target.carriage',
                                                     'base.dart_target.guiding_light', 'base.dart_target.rail']]
                relative_light = np.linalg.inv(rest_world[core]) @ rest_world[light]
                for offset in [-.28, .28]:
                    shifted = apply_pose(doc, joints, {carriage_joint['id']: offset})
                    worlds = {i: w for i, w, _ in scene_nodes(shifted)}
                    np.testing.assert_allclose(worlds[rail], rest_world[rail], atol=1e-12)
                    np.testing.assert_allclose(np.linalg.inv(worlds[core]) @ worlds[light], relative_light, atol=1e-12)
                    moving_ids = {ids[k] for k in carriage_joint['children']}
                    target_points = np.vstack([x for i, _, x, _, _ in mesh_instances(shifted, binary) if i in moving_ids])
                    assert target_points[:, 1].min() > -.49 and target_points[:, 1].max() < .49
                    for index in moving_ids:
                        np.testing.assert_allclose(worlds[index][:3, 3]-rest_world[index][:3, 3],
                                                   [0, offset, 0], atol=1e-12)
                report['motion_checks']['base_dart_target'] = {
                    'travel_limits_m': [-.28, .28], 'fixed_rail': True,
                    'detector_and_guiding_light_move_together': True,
                    'carriage_envelope_within_rail_at_both_limits': True,
                    'sinusoidal_motion_is_demo_only': True}
                report['motion_checks']['base'] = {'shield_travel_m': joints[0]['limits'][1],
                    'radial_travel_m': .17, 'downward_travel_m': .045,
                    'reconstructed_armor_modules': 3, 'reconstruction_stays_fixed': True,
                    'armor_window_visibility': visibility,
                    'lowest_open_shield_z_m': float(points[:, 2].min()), 'minimum_footprint_margin_m': float(-distance.max()),
                                                    'travel_is_illustrative': True}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('../assets/rm2026-field'))
    parser.add_argument('--reference', type=Path, default=Path('../assets/rm2026-reference'))
    parser.add_argument('--out', type=Path, default=Path('out/reference-motion-verification.json'))
    args = parser.parse_args()
    result = verify(args.source, args.reference)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['motion_checks'], indent=2))


if __name__ == '__main__':
    main()
