# SPDX-License-Identifier: MIT OR Apache-2.0
"""Preview-only rig and IK for a relative 100 mm Technology Core translation.

Uses identified CAD links with schematic bearing housings. Never writes this
rig back to the reference GLB or claims physical joint limits or match timing.
"""
import copy
import hashlib

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from gltf_scene import accessor, scene_nodes
from semantic_reconstruction import add_reconstruction
from semantic_geometry import split_geometry


# Numerical guards for the disposable display rig, not measured mechanical stops.
PREVIEW_JOINT_RANGE = (-1.2, 1.2)


def rigid_rotation(origin, axis, angle):
    rotation = Rotation.from_rotvec(np.asarray(axis) * angle).as_matrix()
    result = np.eye(4)
    result[:3, :3] = rotation
    result[:3, 3] = origin - rotation @ origin
    return result


def forward(axes, coordinates):
    result = np.eye(4)
    for (origin, axis), value in zip(axes, coordinates):
        result = result @ rigid_rotation(origin, axis, value)
    return result


def solve_translation(axes, point, direction, distances):
    """Hold tool orientation while translating; bounds are solver guards only."""
    targets = [point + direction * distance for distance in distances]
    return solve_poses(axes, point, targets, [np.eye(3)] * len(targets))


def solve_poses(axes, point, targets, rotations):
    """Track Cartesian tool poses with warm-started IK; fail on unreachable poses."""
    q = np.zeros(len(axes))
    solved, position_errors, angle_errors = [], [], []
    for target, rotation in zip(targets, rotations):
        def residual(values):
            pose = forward(axes, values)
            position = pose[:3, :3] @ point + pose[:3, 3]
            error = Rotation.from_matrix(rotation.T @ pose[:3, :3]).as_rotvec()
            return np.r_[10 * (position-target), error]

        fit = least_squares(residual, q, bounds=PREVIEW_JOINT_RANGE,
                            ftol=1e-11, xtol=1e-11, gtol=1e-11, max_nfev=150)
        q = fit.x
        pose = forward(axes, q)
        pe = np.linalg.norm(pose[:3, :3] @ point + pose[:3, 3] - target)
        ae = np.linalg.norm(Rotation.from_matrix(rotation.T @ pose[:3, :3]).as_rotvec())
        if pe > 1e-5 or ae > 1e-4:
            raise ValueError(f'demo IK did not converge: position={pe}, angle={ae}')
        solved.append(q.copy()); position_errors.append(pe); angle_errors.append(ae)
    return np.asarray(solved), {'maximum_position_error_m': max(position_errors),
                                'maximum_orientation_error_rad': max(angle_errors),
                                'maximum_absolute_joint_angle_rad': float(np.abs(solved).max())}


def sequence_targets(point, direction, phases):
    """A closed, smooth pose tour with a separate 100 mm insertion segment.

    Offsets are in the asset frame. No calibration to the rulebook world frame,
    obstacle clearance, or mechanical joint limits is implied.
    """
    up = np.array([0., 0., 1.])
    side = np.cross(up, direction)
    # Toward-arm, sideways, upward offsets in metres; relative rotation vectors
    # in degrees around those same axes. Each waypoint has zero speed/acceleration.
    offsets = np.array([[0,0,0], [.04,0,.12], [.08,.10,.16],
                        [.08,-.10,.12], [.03,0,.08], [.13,0,.08],
                        [.03,0,.08], [0,0,0]], float)
    turns = np.array([[0,0,0], [0,12,0], [10,18,25],
                      [-10,-12,-25], [0,0,0], [0,0,0], [0,0,0], [0,0,0]], float)
    basis = np.column_stack([direction, side, up])
    targets, rotations = [], []
    for phase in phases:
        segment = min(int(phase * 7), 6)
        t = phase * 7 - segment
        blend = t**3 * (10 - 15*t + 6*t*t)
        offset = offsets[segment] * (1-blend) + offsets[segment+1] * blend
        turn = .5 * (turns[segment] * (1-blend) + turns[segment+1] * blend)
        targets.append(point + basis @ offset)
        rotations.append(Rotation.from_rotvec(basis @ np.radians(turn)).as_matrix())
    return np.asarray(targets), np.asarray(rotations)


def complex_trajectory(axes, point, direction, frames):
    targets, rotations = sequence_targets(point, direction, np.arange(frames) / frames)
    values, report = solve_poses(axes, point, targets, rotations)
    report.update(profile='pose_tour', stages=['lift', 'turn_left', 'sweep_right', 'align',
                  'translate_100mm', 'retract', 'return'],
                  orientation='varies during pose tour; held during 100 mm translation',
                  timing='seven equal-duration quintic segments; illustrative',
                  maximum_tool_displacement_m=float(np.linalg.norm(targets-point, axis=1).max()))
    return values, report


def prepare_demo(document, binary, binding):
    """Build a disposable display rig; verified reference geometry stays untouched."""
    doc = copy.deepcopy(document)
    ids = {n['id']: n['node'] for n in binding['nodes']}
    world = {i: w for i, w, _ in scene_nodes(doc)}
    parents = {i: p for i, _, p in scene_nodes(doc)}
    links = {
        1: ['shoulder.housing'],
        2: ['upper_arm', 'upper_arm.seal_0', 'upper_arm.seal_1', 'upper_arm.seal_2', 'upper_arm.seal_3'],
        3: ['forearm', 'forearm.detail_0', 'forearm.detail_1'],
        6: ['tool.assembly', 'tool.cover', 'tool.side_0', 'tool.side_1'],
    }
    for link, names in links.items():
        parent = ids[f'tech-core.link.{link}']
        for name in names:
            index = ids['tech-core.part.' + name]
            doc['nodes'][parents[index]]['children'].remove(index)
            doc['nodes'][parent].setdefault('children', []).append(index)
            node = doc['nodes'][index]
            for key in ['matrix', 'translation', 'rotation', 'scale']:
                node.pop(key, None)
            node['matrix'] = (np.linalg.inv(world[parent]) @ world[index]).flatten(order='F').tolist()
    # This mixed mesh spans several links. Recover its tool enclosure before
    # hiding the remaining hardware that cannot yet be assigned to rigid links.
    hidden = ids['tech-core.part.shared_joint_hardware']
    shared = doc['meshes'][doc['nodes'][hidden]['mesh']]['primitives'][0]
    fingerprint = hashlib.sha256()
    for attribute in [shared['attributes']['POSITION'], shared['indices']]:
        fingerprint.update(np.ascontiguousarray(accessor(doc, binary, attribute)).tobytes())
    if fingerprint.hexdigest() != '315dfc86ca5ebaa88d7a513755765dabcedc29fa3b0ba977c57b721662c42977':
        raise ValueError('Core demo enclosure partition requires the pinned source hardware mesh')
    # This contiguous source group contains 106 welded components on the tool
    # side of the wrist: enclosure panels, their brackets and attached fittings.
    # Keep the exact source triangles and move them with link 6 before hiding
    # the remaining mixed bearing hardware. No geometric threshold runs here.
    enclosure = len(doc['nodes'])
    doc, binary, _ = split_geometry(doc, binary, {'geometry_groups': [{
        'select': {'name': doc['nodes'][hidden]['name']},
        'parent': {'name': doc['nodes'][ids['tech-core.link.6']]['name']},
        'name': 'demo/tech-core/source_tool_enclosure',
        'parts': [{'primitive': 0, 'triangle_ranges': [[91775, 118288]]}],
        'metadata': {'id': 'demo.tech-core.source_tool_enclosure', 'roles': ['assembly']},
        'evidence': ['Reviewed tool-side components of the checksum-pinned shared hardware mesh; 26513 original enclosure and fitting triangles.']
    }]})
    doc['nodes'][hidden].pop('mesh')
    joints = binding['joints']
    frames = {i: w for i, w, _ in scene_nodes(doc)}
    axes = [(frames[j['origin_node']][:3, 3],
             frames[j['origin_node']][:3, :3] @ np.asarray(j['axis'])) for j in joints]
    diagonal = np.array([2**-.5, 2**-.5, 0])
    housings = [
        ('base_mount', 0, [.274431789, -.055234488, .038], [0, 0, 1], .076, .076),
        ('shoulder', 1, [.173, -.156666277, .162300324], diagonal, .076, .110),
        ('elbow', 2, [.120, -.114023133, .80575599], diagonal, .059, .155),
        ('wrist_1', 3, [-.062, .04939196, .257171943], diagonal, .0435, .080),
        ('wrist_2', 4, [-.087828496, .022344201, .306564419], axes[4][1], .0375, .140),
        ('tool_flange', 5, [-.09, .0245, .3595], axes[5][1], .0375, .090),
    ]
    additions = []
    for name, link, center, axis, radius, length in housings:
        axis = np.asarray(axis, dtype=float); axis /= np.linalg.norm(axis)
        seed = np.array([1., 0, 0]) if abs(axis[0]) < .9 else np.array([0., 1, 0])
        x = np.cross(seed, axis); x /= np.linalg.norm(x)
        y = np.cross(axis, x)
        matrix = np.eye(4); matrix[:3, :3] = np.column_stack([x, y, axis]); matrix[:3, 3] = center
        parent = ids['tech-core'] if link == 0 else ids[f'tech-core.link.{link}']
        additions.append({'type': 'tapered_prism', 'name': 'demo/tech-core/' + name,
            'parent': {'name': doc['nodes'][parent]['name']},
            'profile': {'sides': 48, 'radius_m': [radius, radius], 'z_range_m': [-length/2, length/2], 'center_xy_m': [0, 0]},
            'matrix': matrix.flatten(order='F').tolist(),
            'material': {'name': 'schematic_bearing', 'pbrMetallicRoughness': {
                'baseColorFactor': [.32, .34, .37, 1], 'metallicFactor': .5, 'roughnessFactor': .6}},
            'metadata': {'id': 'demo.tech-core.' + name, 'roles': ['assembly'], 'layer': 'reconstruction'},
            'evidence': ['Preview-only schematic bearing; radius follows identified CAD cylinders, length and link ownership are illustrative.']})
    doc, binary, _ = add_reconstruction(doc, binary, {'geometry_additions': additions}, '.')
    after = {i: w for i, w, _ in scene_nodes(doc)}
    for index, matrix in world.items():
        np.testing.assert_allclose(after[index], matrix, atol=1e-10)
    # A point on the copied tool defines a rigid tool reference. Translation with
    # fixed orientation is the same 100 mm for every point on that tool.
    tool = doc['nodes'][ids['tech-core.part.tool.assembly']]
    p = doc['meshes'][tool['mesh']]['primitives'][6]
    xyz = accessor(doc, binary, p['attributes']['POSITION'])
    xyz = xyz[np.unique(accessor(doc, binary, p['indices']))]
    point = (xyz.min(0) + xyz.max(0))/2
    direction = -np.asarray(axes[-1][1]).copy(); direction[2] = 0
    direction /= np.linalg.norm(direction)
    report = {'kind': 'preview_only_cad_links_with_schematic_bearings',
              'rulebook': 'V2.1.0 section 5.3.3, Level 2 post-insertion translation: 100 mm',
              'translation_m': .1, 'direction_in_asset_frame': direction.tolist(),
              'tool_reference_m': point.tolist(),
              'orientation': 'held at CAD rest orientation',
              'timing': 'illustrative cosine out-and-back; no match controller',
              'absolute_rulebook_frame_calibrated': False,
              'hidden_shared_hardware_node': hidden,
              'hidden_hardware_triangles': 91775,
              'restored_tool_enclosure_node': enclosure,
              'restored_tool_enclosure_triangles': 26513,
              'tool_enclosure_partition_sha256': fingerprint.hexdigest(),
              'schematic_bearings': [a['name'] for a in additions]}
    for joint in binding['joints']:
        display_joint = doc['nodes'][joint['motion_node']]['extras']['rm']['joint']
        display_joint['preview_range'] = list(PREVIEW_JOINT_RANGE)
        display_joint['preview_range_source'] = 'CAD display-rig numerical guards; not physical limits'
    report['preview_joint_range_rad'] = list(PREVIEW_JOINT_RANGE)
    return doc, binary, axes, point, direction, report


def trajectory(axes, point, direction, frames):
    distances = .05 * (1 - np.cos(2*np.pi*np.arange(frames)/frames))
    return solve_translation(axes, point, direction, distances)
