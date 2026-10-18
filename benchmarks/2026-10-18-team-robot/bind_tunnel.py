#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-preserving PIE/Future tunnel bindings; no vertex scaling or hole-fit offsets."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,write_glb,mesh_instances,scene_nodes
from robot_armor import identify_armor,strip_armor_surfaces
C=np.array([[0,0,1],[1,0,0],[0,1,0.]])
BODY=np.array([-.04133,.18,.09173])
PROFILE="heavy"


def joint(name,parent,pivot,axis=(1,0,0),angle=0,translation=(0,0,0)):
    return dict(name=name,parent=parent,pivot_m=(C@(np.array(pivot)-BODY)).tolist(),axis=(C@np.array(axis)).tolist(),angle_rad=angle,
                translation_m=(C@np.array(translation)).tolist(),drive='Transform',collision=None)


def anatomy(path):
    if PROFILE=='infantry':
        wheels={'1/3/2/1':'wheel-0','1/2/2/1':'wheel-1','1/1/2/1':'wheel-2','1/4/2/1':'wheel-3'}
        for prefix,name in wheels.items():
            if path==prefix or path.startswith(prefix+'/'):return name
        if path.startswith('1/302/'):
            index=int(path.split('/')[2])
            if index in {27,28,29}:return 'pitch-crank'
            if index in {30,34,37}:return 'pitch-rod'
            if index in {1,2,8,12,13,14,15,22,23,24,25,35,36,38,39,40,41,42,43,44,45,62,109,128}:return 'pitch'
            # Lower yaw bearing inner pieces attach to the deck.
            if any(path==p or path.startswith(p+'/') for p in ['1/302/6/2','1/302/6/3','1/302/6/17','1/302/6/18']):return 'source-body'
            return 'yaw'
        return 'source-body'
    motors=['1/1/1/10','1/1/2/11','1/1/3/10','1/1/4/10','1/2/8/1']
    if any(path.startswith(p+'/2/') for p in motors):return None # reviewed dangling motor leads; user-approved cord removal
    wheels={'1/1/3/1':'wheel-0','1/1/2/7':'wheel-1','1/1/1/3':'wheel-2','1/1/4/9':'wheel-3'}
    for prefix,name in wheels.items():
        if path==prefix or path.startswith(prefix+'/'):return name
    if path.startswith('1/2/6/'):return 'camera-lift'
    if path.startswith('1/2/5/') or path.startswith('1/2/3/21/11'):return 'uwb'
    if path.startswith('1/2/2/'):return 'shoulder'
    if any(path.startswith('1/2/'+str(i)+'/') for i in [3,4,7,8]):return 'elbow'
    if path=='1/2/10':return 'elbow'
    return 'source-body'


def poses(joints,value,aim=(0,0)):
    deltas=[];result=[]
    for j in joints:
        amount=value if j['drive']=='Transform' else aim[0] if j['drive']=='Yaw' else aim[1]
        pivot=np.array(j['pivot_m']);change=np.eye(4);change[:3,:3]=Rotation.from_rotvec(np.array(j['axis'])*j['angle_rad']*amount).as_matrix()
        change[:3,3]=pivot-change[:3,:3]@pivot+np.array(j['translation_m'])*amount
        delta=(np.eye(4) if j['parent'] is None else deltas[j['parent']])@change;deltas.append(delta)
        frame=np.eye(4);frame[:3,3]=pivot;result.append(delta@frame)
    return result


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    global BODY,PROFILE
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--source",choices=["heavy","infantry"],default="heavy");p.add_argument('--sources',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--base-config',type=Path,required=True);a=p.parse_args()
    PROFILE=a.source
    model='pie-2026-tunnel-engineer' if PROFILE=='heavy' else 'qingdao-2026-infantry'
    profile='pie-tunnel-heavy-v1' if PROFILE=='heavy' else 'future-tunnel-infantry-v1'
    if PROFILE=='infantry':BODY=np.array([.0055,.12,0.])
    base=a.sources/(model+'-pilot/package');source=json.loads(Path(__file__).with_name('candidates.json').read_text())['sources']['tunnel_heavy' if PROFILE=='heavy' else 'tunnel_infantry']
    assert sha(a.sources/(model+'.step'))==source['cad_sha256']
    rows=json.loads((a.sources/(model+'-hierarchy.json')).read_text());owners={sid:r['path'] for r in rows for sid in r.get('native_solids',[])}
    d,b=read_glb(base/'materials.glb');original=copy.deepcopy(d)
    heading=np.arctan2(.8255124,.5643839);gimbal_rotation=Rotation.from_rotvec([0,-heading,0]).as_matrix()
    yaw_pivot=np.array([.0055,.08557,0.]);gimbal_transform=np.eye(4);gimbal_transform[:3,:3]=gimbal_rotation;gimbal_transform[:3,3]=yaw_pivot-gimbal_rotation@yaw_pivot
    if PROFILE=='infantry':
        worlds={ni:m for ni,m,_ in scene_nodes(d)}
        for ni,matrix in worlds.items():
            if 'mesh' not in d['nodes'][ni]:continue
            e=d['nodes'][ni].get('extras',{});path=e.get('source_leaf_path') or owners.get(e.get('native_solid_index'),'')
            if path.startswith('1/302/') and anatomy(path)!='source-body':matrix=gimbal_transform@matrix
            for k in ['translation','rotation','scale','children']:d['nodes'][ni].pop(k,None)
            d['nodes'][ni]['matrix']=matrix.flatten(order='F').tolist()
        d['scenes']=[dict(nodes=[ni for ni in worlds if 'mesh' in d['nodes'][ni]])];d['scene']=0
    armor=identify_armor(d,b,rows);assert len(armor['modules'])==4
    for m in armor['modules']:
        matrix=np.array(m['face_matrix_gltf']).reshape(4,4,order='F');r=C@matrix[:3,:3];q=Rotation.from_matrix(r).as_quat()
        m['body_face_pose_flu']=dict(translation_m=(C@(matrix[:3,3]-BODY)).tolist(),rotation_wxyz=q[[3,0,1,2]].tolist())
        m['id']=int(np.round(np.arctan2(r[1,0],r[0,0])/(np.pi/2)))%4
    armor['modules'].sort(key=lambda m:m['id']);armor['runtime_replacement']=True;strip_armor_surfaces(d,armor)
    axis=np.array([.999594,0,-.0284937]);axis/=np.linalg.norm(axis)
    uwb_axis=np.array([.0284937,0,.999594]);uwb_axis/=np.linalg.norm(uwb_axis)
    joints=[joint('source-body',None,BODY),joint('shoulder',0,[-.037747,.2280719,.2136342],axis,-np.deg2rad(7)),
            joint('elbow',1,[-.05,.2743823,-.1633],axis,np.deg2rad(7)),
            joint('camera-lift',2,[.07906,.27503,.02971],translation=[0,-.0494975,-.0494975]),
            joint('uwb',2,[.07083,.22038,-.06684],uwb_axis,-np.deg2rad(20))]
    if PROFILE=='infantry':
        axis=np.array([1.,0,0]);joints=[joint('source-body',None,BODY),joint('yaw',0,yaw_pivot,axis=(0,1,0),angle=1),
            joint('pitch',1,[.0055,.1846206,0],axis=axis,angle=-1),
            joint('pitch-crank',1,[.086,.1236206,.004],axis=axis,angle=-1),
            joint('pitch-rod',1,[-.039,.1846206,.065],axis=axis,angle=-1)]
        for j in joints[1:]:j['drive']='Yaw' if j['name']=='yaw' else 'Pitch'
    worlds={ni:m for ni,m,_ in scene_nodes(d)};by_node={};removed=[];source_triangles=0
    for ni,pi,points,t,mi in mesh_instances(d,b):
        e=d['nodes'][ni]['extras'];path=e.get('source_leaf_path') or owners.get(e.get('native_solid_index'),'');name=anatomy(path)
        if name is None:removed.append(dict(node=ni,path=path,triangles=len(t)));continue
        by_node[ni]=(name,path);source_triangles+=len(t)
    reference=poses(joints,0);group_points={j['name']:[] for j in joints};wheel_points={f'wheel-{i}':[] for i in range(4)}
    for ni,pi,points,t,mi in mesh_instances(d,b):
        if ni not in by_node:continue
        name,_=by_node[ni];flu=(points-BODY)@C.T
        if name.startswith('wheel-'):wheel_points[name].append(flu)
        elif d['nodes'][ni]['extras'].get('native_solid_index',0)>0:group_points[name].append(flu)
    for j,frame in zip(joints,reference):
        pts=np.concatenate(group_points[j['name']]);local=pts-frame[:3,3]
        r=Rotation.from_rotvec((C@axis)*np.deg2rad(7)).as_matrix() if j['name']=='shoulder' else np.eye(3)
        aligned=local@r;lo=aligned.min(0);hi=aligned.max(0);q=Rotation.from_matrix(r).as_quat()
        j['collision']=dict(center_m=(r@((lo+hi)/2)).tolist(),half_m=(np.maximum((hi-lo)/2,.001)).tolist(),rotation_wxyz=q[[3,0,1,2]].tolist())
    hubs=[(np.concatenate(wheel_points[f'wheel-{i}']).min(0)+np.concatenate(wheel_points[f'wheel-{i}']).max(0))/2 for i in range(4)]
    # Chassis wheel axes are level in operation; source suspension poses differ.
    hub_z=float(np.median([v[2] for v in hubs]));hubs=[np.array([v[0],v[1],hub_z]) for v in hubs]
    config=json.loads(a.base_config.read_text());config=config.get('config',config)
    config.update(climbing=None,folding=None,team_cad=False,omni_frame=None,mecanum=True,mass_kg=28.,body_half_m=[.27,.26,.008],
                  hub_drop_m=-hub_z-.03+28*9.81/40000,wheel_radius_m=.076,wheel_width_m=.045,
                  wheel_hubs_m=[v[:2].tolist() for v in hubs],suspension_rest_m=.03,suspension_stiffness_n_m=10000.,suspension_damping_n_s_m=500.,
                  turret_center_m=[.1,0,.06],turret_half_m=[.01,.01,.01])
    config['articulation']=dict(profile=profile,limit_rad=1. if PROFILE=='heavy' else 0.,speed_rad_s=.65,joints=joints,muzzle_offset_m=[.2,0,0],camera_offset_m=[.13,0,.01],armor_faces=[m['body_face_pose_flu'] for m in armor['modules']])
    if PROFILE=='infantry':
        config.update(mecanum=False,mass_kg=16.,body_half_m=[.29,.24,.006],wheel_radius_m=.065,wheel_width_m=.035,
            hub_drop_m=-hub_z-.03+16*9.81/40000,turret_center_m=[0,0,.0646206])
        # Fitted source muzzle and camera centre after neutralizing source gimbal yaw.
        for path,key in [('1/302/8','muzzle_offset_m'),('1/302/14','camera_offset_m')]:
            pts=[]
            for ni,pi,point,t,mi in mesh_instances(d,b):
                e=d['nodes'][ni]['extras'];owner=e.get('source_leaf_path') or owners.get(e.get('native_solid_index'),'')
                if owner==path or owner.startswith(path+'/'):pts.append((point-BODY)@C.T)
            point=np.concatenate(pts);center=(point.min(0)+point.max(0))/2;center-=np.array(joints[2]['pivot_m'])
            if key=='muzzle_offset_m':center[0]=point[:,0].max()-joints[2]['pivot_m'][0]
            config['articulation'][key]=center.tolist()
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'chassis.json').write_text(json.dumps(config,indent=2)+'\n');files={'chassis':dict(file='chassis.json',sha256=sha(a.out/'chassis.json'))};stats={}
    for name,value in ([('neutral',0),('mid-stow',.5),('stowed',1)] if PROFILE=='heavy' else [('neutral',0)]):
        out=copy.deepcopy(d);bones={};target_frames={j['name']:f for j,f in zip(joints,poses(joints,value))}
        for i,hub in enumerate(hubs):
            f=np.eye(4);f[:3,3]=hub
            if PROFILE=='infantry':f[:3,:3]=Rotation.from_rotvec([0,0,np.arctan2(hub[1],hub[0])-np.pi/2]).as_matrix()
            target_frames[f'wheel-{i}']=f
        for key,flu in target_frames.items():
            native=np.eye(4);native[:3,:3]=C.T@flu[:3,:3]@C;native[:3,3]=C.T@flu[:3,3]
            bones[key]=len(out['nodes']);out['nodes'].append(dict(name='link/'+key,matrix=native.flatten(order='F').tolist(),children=[]))
        for ni,(key,path) in by_node.items():
            node=copy.deepcopy(d['nodes'][ni]);node.pop('children',None)
            for k in ['translation','rotation','scale']:node.pop(k,None)
            if key.startswith('wheel-'):
                # Match per-wheel source axle centre before rebasing to level suspension.
                pts=np.concatenate(wheel_points[key]);pivot=(pts.min(0)+pts.max(0))/2
            else:pivot=np.array(joints[next(i for i,j in enumerate(joints) if j['name']==key)]['pivot_m'])
            original_body=worlds[ni].copy();original_body[:3,3]-=BODY
            original_body[:3,3]-=C.T@pivot
            if key.startswith('wheel-') and PROFILE=='infantry':
                rest_rotation=C.T@target_frames[key][:3,:3]@C
                original_body[:3,:3]=rest_rotation.T@original_body[:3,:3];original_body[:3,3]=rest_rotation.T@original_body[:3,3]
            node['matrix']=original_body.flatten(order='F').tolist();node['extras'].update(motion_group=key,source_occurrence_path=path,articulation_bound=True)
            out['nodes'][bones[key]]['children'].append(len(out['nodes']));out['nodes'].append(node)
        out['scenes']=[dict(nodes=list(bones.values()))];out['scene']=0
        out['asset'].setdefault('extras',{})['armor_bindings']=armor
        target=a.out/(name+'.glb');write_glb(target,out,b)
        written,payload=read_glb(target);assert payload==b,'source geometry buffer changed'
        assert sum(len(t) for _,_,_,t,_ in mesh_instances(written,payload))==source_triangles
        files[name]=dict(file=target.name,sha256=sha(target))
        pts=np.concatenate([v for _,_,v,_,_ in mesh_instances(out,b)]);stats[name]=dict(input_rad=value,bounds_gltf_m=[pts.min(0).tolist(),pts.max(0).tolist()],height_above_loaded_floor_m=float(pts[:,1].max()+config['wheel_radius_m']-hub_z))
    manifest=dict(schema=4,profile=profile,source=source,files=files,armor=armor,poses=stats,retained_triangles=source_triangles,
                  geometry_buffers_exact=True,base_config_sha256=sha(a.base_config),removed_motor_leads=removed,input_sha256=sha(base/'materials.glb'),producer_sha256=sha(Path(__file__)),
                  policy=('Fixed-height source; yaw neutralized to the barrel direction, firing stage and pitch linkage prescribed from fitted bearings; no chassis scaling.' if PROFILE=='infantry' else '7-degree shoulder leveling with counter-rotating elbow; 70 mm camera travel along source 45-degree rail; UWB hinge retracts 20 degrees. Source-fit prescribed stow, not full manipulation or torque calibration. Motor leads cut; mesh buffers and source materials retained byte-for-byte.'))
    (a.out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');(a.out/'CAD-NOTICE.md').write_text(source['credit']+'\n'+source['source_article']+'\n'+source['terms']+'\n'+manifest['policy']+'\n')
    print(json.dumps(stats,indent=2))


if __name__=='__main__':main()
