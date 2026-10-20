#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Bind the checksum-pinned EGA Sentry; source meshes retain their vertex buffers.

The SolidWorks export is Y-up. Bearings locate the two pitch axes 125 mm apart.
Source bearing pairs define the head/pitch and UWB parallelograms. Their
followers share the lift angle; counter-rotating carriers close each linkage.
The endpoint/rate remain simulator policy, not recovered controller calibration.
"""
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
from gltf_scene import read_glb, write_glb, mesh_instances, scene_nodes
from robot_armor import identify_armor, strip_armor_surfaces

# GLB right/up/back-like source basis to the renderer's native FLU convention.
C = np.array([[0., 0., 1.], [1., 0., 0.], [0., 1., 0.]])
# Source gun is clocked 32 degrees around Y; align its barrel with body +x.
F = np.array([[-np.cos(np.deg2rad(32)), 0., np.sin(np.deg2rad(32))],
              [np.sin(np.deg2rad(32)), 0., np.cos(np.deg2rad(32))], [0., 1., 0.]])
MODEL = 'ega-2026-tunnel-sentry'
PROFILE = 'ega-tunnel-sentry-v1'
WHEELS = {'1/2/2': 'wheel-0', '1/2/12': 'wheel-1', '1/3/2': 'wheel-2', '1/3/12': 'wheel-3'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def anatomy(path):
    for prefix, name in WHEELS.items():
        if path == prefix or path.startswith(prefix + '/'):
            return name
    if path.startswith('1/12/'):
        index = int(path.split('/')[2])
        if index == 90:
            return 'pitch'
        if index in {32,36,37,39,41,44,46,92,93}:
            return 'pitch'
        if index in {31,34,35,43,45,48}:
            return 'lower-pitch'
        if index == 33:
            return 'pitch-rod'
        if index in {1,38,40,42,47,49,50,55,91}:
            return 'lift'
        if index == 59:
            return 'uwb-rod'
        if 54 <= index <= 89 and index not in {70,71}:
            return 'uwb-carrier'
        return 'yaw'
    # The upper support, feeder and electronics platform attach to the big yaw.
    if path.startswith(('1/7/', '1/14/', '1/17/')) or path == '1/13':
        return 'yaw'
    if path.startswith('1/5/') and int(path.split('/')[2]) in {1,5,6,7}:
        return 'yaw'
    return 'source-body'


def joint(name, parent, pivot, axis=(0.,1.,0.), angle=0., drive='Transform'):
    return dict(name=name, parent=parent, pivot_m=pivot.tolist(), axis=list(axis),
                angle_rad=angle, translation_m=[0.,0.,0.], drive=drive, collision=None)


def frames(joints, value, aim=(0.,0.)):
    deltas, poses = [], []
    for j in joints:
        amount = value if j['drive'] == 'Transform' else aim[0] if j['drive'] == 'Yaw' else aim[1]
        pivot = np.array(j['pivot_m'])
        change = np.eye(4)
        change[:3,:3] = Rotation.from_rotvec(np.array(j['axis']) * j['angle_rad'] * amount).as_matrix()
        change[:3,3] = pivot - change[:3,:3] @ pivot
        delta = (np.eye(4) if j['parent'] is None else deltas[j['parent']]) @ change
        deltas.append(delta)
        frame = delta.copy(); frame[:3,3] += delta[:3,:3] @ pivot
        poses.append(frame)
    return poses


def linkage_joints(lower, upper):
    """Build the source-derived two parallelograms; coordinates are FLU metres."""
    # Fit the parallelograms in body FLU. Dimensions are drawing/mesh fits:
    # head tie-rod A=(28,111.14), B=(28,236.14) mm; Q-P = B-A = 125 mm.
    # UWB A=(27.5,84.57), C=(50,182.01), B=(22.5,229.64) mm;
    # B-P = C-A = (22.5,97.44) mm. No independent UWB actuator is invented.
    pitch_a = np.array([.028, -.10055, .11114-.12])
    uwb_a = np.array([.0275, .149, .08457-.12])
    uwb_b = np.array([.0225, .175, .22964-.12])
    # Slightly below horizontal. This endpoint is a simulator posture policy;
    # pivots, rod lengths, scale and source wheel geometry are unchanged.
    fold = np.deg2rad(100.)
    return [joint('source-body',None,np.zeros(3)),
              joint('yaw',0,np.zeros(3),axis=(0.,0.,1.),angle=1.,drive='Yaw'),
              joint('lift',1,lower,angle=fold),
              joint('head-level',2,upper,angle=-fold),
              joint('pitch',3,upper,angle=-1.,drive='Pitch'),
              joint('lower-pitch',1,lower,angle=-1.,drive='Pitch'),
              joint('pitch-rod-level',5,pitch_a,angle=1.,drive='Pitch'),
              joint('pitch-rod',6,pitch_a,angle=fold),
              joint('uwb-carrier',2,uwb_b,angle=-fold),
              joint('uwb-rod',1,uwb_a,angle=fold)]


def validate_linkages(joints):
    """Check both rod ends throughout folding and independent gimbal motion.

    Verify closed chains, not just endpoint heights: a guessed independent UWB
    hinge or a pitch follower attached to the wrong parent must fail here.
    """
    lower = np.array(joints[2]['pivot_m'])
    upper = np.array(joints[3]['pivot_m'])
    pitch_a = np.array(joints[7]['pivot_m'])
    pitch_b = pitch_a + upper-lower
    uwb_a = np.array(joints[9]['pivot_m'])
    uwb_b = np.array(joints[8]['pivot_m'])
    uwb_c = uwb_a + uwb_b-lower
    maximum = 0.
    for value in np.linspace(0.,1.,21):
        for aim in [(0.,0.),(.6,.25),(-.8,-.3)]:
            pose = frames(joints,value,aim)
            def located(index, point):
                return pose[index][:3,:3] @ (point-np.array(joints[index]['pivot_m'])) + pose[index][:3,3]
            for left,right,point in [(5,7,pitch_a),(4,7,pitch_b),(2,8,uwb_b),(8,9,uwb_c),(1,9,uwb_a)]:
                maximum = max(maximum,float(np.linalg.norm(located(left,point)-located(right,point))))
    if maximum > 1e-8:
        raise ValueError(f'source four-bar closure violated: {maximum} m')
    return dict(max_rod_endpoint_error_m=maximum,fold_samples=21,aim_samples=3,
                source_fit='Pitch rod: 125 mm. UWB follower: hypot(22.5,97.44) mm. Bearing fits from exported CAD.')


def collision_box(points, pivot, chassis=False):
    """Enclose every source point; align the fixed body with its chassis axes.

    The barrel-rest FLU frame is clocked 32 degrees from the chassis. An AABB
    in that frame fills empty wheel-bay corners; the source-axis OBB preserves
    all points while allowing the real X-wheel stance to approach ramps.
    """
    basis = Rotation.from_euler('z', -32., degrees=True).as_matrix() if chassis else np.eye(3)
    local = (points-pivot) @ basis
    lo, hi = local.min(0), local.max(0)
    q = Rotation.from_matrix(basis).as_quat()
    center = basis @ ((lo+hi)/2)
    half = np.maximum((hi-lo)/2,.001)
    assert np.max(np.abs((points-pivot-center) @ basis)-half) < 1e-12
    return dict(center_m=center.tolist(),half_m=half.tolist(),rotation_wxyz=q[[3,0,1,2]].tolist())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--base-config', type=Path, required=True)
    a = p.parse_args()
    source = json.loads(Path(__file__).with_name('candidates.json').read_text())['sources']['tunnel_sentry']
    assert digest(a.sources / (MODEL + '.step')) == source['cad_sha256']
    rows = json.loads((a.sources / (MODEL + '-hierarchy.json')).read_text())
    owners = {sid:r['path'] for r in rows for sid in r.get('native_solids',[]) if sid > 0}
    base = a.sources / (MODEL + '-pilot/package')
    d,b = read_glb(base / 'materials.glb')
    armor = identify_armor(d,b,rows)
    assert len(armor['modules']) == 4
    # Body origin at the source deck; no nonuniform scaling or clearance offsets.
    world = {ni:m for ni,m,_ in scene_nodes(d)}
    center = json.loads((a.sources / (MODEL + '-frame.json')).read_text())['source_center_mm']
    body_source = np.array([0.,.12,0.])
    body = np.array(d['nodes'][0]['matrix']).reshape(4,4,order='F')
    origin = body[:3,:3] @ (body_source-np.array(center)/1000) + body[:3,3]
    def flu(points):
        return (points-origin) @ F.T
    for m in armor['modules']:
        frame = np.array(m['face_matrix_gltf']).reshape(4,4,order='F')
        q = Rotation.from_matrix(F @ frame[:3,:3]).as_quat()
        m['body_face_pose_flu'] = dict(translation_m=flu(frame[:3,3]).tolist(), rotation_wxyz=q[[3,0,1,2]].tolist())
        direction = F @ frame[:3,0]
        m['id'] = int(np.round(np.arctan2(direction[1],direction[0])/(np.pi/2))) % 4
    armor['modules'].sort(key=lambda m:m['id'])
    assert [m['id'] for m in armor['modules']] == list(range(4))
    armor['runtime_replacement'] = True
    strip_armor_surfaces(d,armor)
    lower = F @ (np.array([0.,.1322,0.])-body_source)
    upper = F @ (np.array([0.,.2572,0.])-body_source)
    joints = linkage_joints(lower, upper)
    closure = validate_linkages(joints)
    original_points = {(ni,pi):flu(points) for ni,pi,points,t,mi in mesh_instances(d,b)}
    group_points = {j['name']:[] for j in joints}
    wheel_points = {v:[] for v in WHEELS.values()}
    by_node = {}
    triangles = 0
    for ni,pi,points,t,mi in mesh_instances(d,b):
        e = d['nodes'][ni]['extras']
        path = e.get('source_leaf_path') or owners.get(e.get('native_solid_index'),'')
        assert path, f'unclassified source mesh {ni}'
        name = anatomy(path); by_node[ni] = name,path; triangles += len(t)
        (wheel_points if name.startswith('wheel-') else group_points)[name].append(flu(points))
    hubs = []
    for name in WHEELS.values():
        pts = np.concatenate(wheel_points[name]); hubs.append((pts.min(0)+pts.max(0))/2)
    hub_z = float(np.median([v[2] for v in hubs]))
    radius = float(np.median([np.ptp(np.concatenate(wheel_points[n])[:,2])/2 for n in WHEELS.values()]))
    for j in joints:
        if not group_points[j['name']]:
            continue  # Constraint/carrier frames may have no independently owned mesh.
        pts = np.concatenate(group_points[j['name']]); pivot = np.array(j['pivot_m'])
        # Preserve the empty wheel bays; boxes enclose independently moving groups.
        j['collision'] = collision_box(pts,pivot,chassis=j['name']=='source-body')
    config = json.loads(a.base_config.read_text()); config = config.get('config',config)
    config.update(climbing=None,folding=None,team_cad=False,omni_frame=None,mecanum=False,mass_kg=20.,
                  body_half_m=[.19,.19,.006],hub_drop_m=-hub_z-.025,
                  wheel_radius_m=radius,wheel_width_m=.032,wheel_hubs_m=[v[:2].tolist() for v in hubs],
                  suspension_rest_m=.025,suspension_stiffness_n_m=10000.,suspension_damping_n_s_m=500.,
                  turret_center_m=upper.tolist(),turret_half_m=[.01,.01,.01])
    # Source wheel pose is the nominal/unloaded ray anchor. Let gravity produce
    # the ordinary spring sag; do not add a preload height to cancel it.
    spring_sag = config['mass_kg']*9.81/(4*config['suspension_stiffness_n_m'])
    loaded_height = radius+config['hub_drop_m']+config['suspension_rest_m']-spring_sag
    # Muzzle tip and lens are measured from their named source shells after cook.
    offsets = {}
    for prefix,key in [('1/12/90/3','muzzle_offset_m'),('1/12/90/14','camera_offset_m')]:
        pts = np.concatenate([flu(points) for ni,pi,points,t,mi in mesh_instances(d,b)
                              if by_node[ni][1] == prefix or by_node[ni][1].startswith(prefix+'/')])
        v = (pts.min(0)+pts.max(0))/2-upper
        if key == 'muzzle_offset_m': v[0] = pts[:,0].max()-upper[0]
        offsets[key] = v.tolist()
    config['articulation'] = dict(profile=PROFILE,limit_rad=1.,speed_rad_s=.65,joints=joints,
                                armor_faces=[m['body_face_pose_flu'] for m in armor['modules']],**offsets)
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'chassis.json').write_text(json.dumps(config,indent=2)+'\n')
    files = {'chassis':dict(file='chassis.json',sha256=digest(a.out/'chassis.json'))}
    stats = {}
    for pose,value in [('neutral',0.),('mid-stow',.5),('stowed',1.)]:
        out = copy.deepcopy(d); bones = {}; target = {j['name']:m for j,m in zip(joints,frames(joints,value))}
        for i,hub in enumerate(hubs):
            m = np.eye(4); m[:3,3] = hub
            m[:3,:3] = Rotation.from_rotvec([0.,0.,np.arctan2(hub[1],hub[0])-np.pi/2]).as_matrix()
            target[f'wheel-{i}'] = m
        for name,matrix in target.items():
            native = np.eye(4); native[:3,:3] = C.T @ matrix[:3,:3] @ C; native[:3,3] = C.T @ matrix[:3,3]
            bones[name] = len(out['nodes']); out['nodes'].append(dict(name='link/'+name,matrix=native.flatten(order='F').tolist(),children=[]))
        for ni,(name,path) in by_node.items():
            node = copy.deepcopy(d['nodes'][ni]); node.pop('children',None)
            for key in ['translation','rotation','scale']:node.pop(key,None)
            # Source buffer is unchanged; transform the cooked coordinates into
            # the reference joint frame, then let the bone own all future motion.
            original = world[ni]
            body_matrix = np.eye(4); body_matrix[:3,:3] = F @ original[:3,:3]; body_matrix[:3,3] = F @ (original[:3,3]-origin)
            reference = np.eye(4)
            if name.startswith('wheel-'):
                reference = target[name]
            else:reference[:3,3] = joints[next(i for i,j in enumerate(joints) if j['name']==name)]['pivot_m']
            local = np.linalg.inv(reference) @ body_matrix
            native = np.eye(4); native[:3,:3] = C.T @ local[:3,:3]; native[:3,3] = C.T @ local[:3,3]
            node['matrix'] = native.flatten(order='F').tolist()
            node['extras'].update(motion_group=name,source_occurrence_path=path,source_mesh_node=ni,articulation_bound=True)
            out['nodes'][bones[name]]['children'].append(len(out['nodes'])); out['nodes'].append(node)
        out['scenes'] = [dict(nodes=list(bones.values()))]; out['scene'] = 0
        out['asset'].setdefault('extras',{})['armor_bindings'] = armor
        path = a.out/(pose+'.glb'); write_glb(path,out,b)
        written,payload = read_glb(path); assert payload == b
        assert sum(len(t) for _,_,_,t,_ in mesh_instances(written,payload)) == triangles
        neutral_error = 0.
        if value == 0.:
            for ni,pi,points,t,mi in mesh_instances(written,payload):
                source_node = written['nodes'][ni]['extras']['source_mesh_node']
                error = np.max(np.abs(points @ C.T-original_points[source_node,pi]))
                neutral_error = max(neutral_error,float(error))
            assert neutral_error < 1e-7, neutral_error
        points = np.concatenate([p for _,_,p,_,_ in mesh_instances(written,payload)])
        stats[pose] = dict(bounds_gltf_m=[points.min(0).tolist(),points.max(0).tolist()],
                           height_above_loaded_floor_m=float(points[:,1].max()+loaded_height),
                           height_above_nominal_source_floor_m=float(points[:,1].max()+radius-hub_z),
                           neutral_max_coordinate_error_m=neutral_error if value == 0. else None)
        files[pose] = dict(file=path.name,sha256=digest(path))
    manifest = dict(schema=4,profile=PROFILE,source=source,files=files,armor=armor,poses=stats,retained_triangles=triangles,
                    geometry_buffers_exact=True,source_body_collision_frame='source-chassis-axes-minus-32deg-v1',
                    source_body_collision_contains_all_vertices=True,linkage_closure=closure,loaded_suspension_sag_m=spring_sag,input_sha256=digest(base/'materials.glb'),producer_sha256=digest(Path(__file__)),
                    base_config_sha256=digest(a.base_config),
                    hierarchy_sha256=digest(a.sources/(MODEL+'-hierarchy.json')),
                    source_frame_sha256=digest(a.sources/(MODEL+'-frame.json')),
                    source_deck_origin_gltf_m=origin.tolist(),body_from_source_rotation=F.tolist(),
                    policy='Source-fitted pitch and UWB parallelograms, with a policy 100-degree lift endpoint and counter-rotating carriers. No independent UWB hinge actuator. Four independent ray-wheel/suspension forces, ideal omni tyres; actuator speeds, mass and suspension are simulator assumptions, not calibrated EGA dynamics. Nominal source wheel anchors are not raised to cancel spring sag; gravity settles the assumed suspension. No source scaling or direct height teleport.')
    (a.out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (a.out/'CAD-NOTICE.md').write_text(source['credit']+'\n'+source['source_article']+'\n'+source['terms']+'\n'+manifest['policy']+'\n')
    print(json.dumps(stats,indent=2))


if __name__ == '__main__':
    main()
