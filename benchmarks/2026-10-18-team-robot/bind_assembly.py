#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-preserving PIE six-axis arm and RMUC2027 Technology Core workbench rig.

Bindings are reviewed kinematic hypotheses, not firmware limits or force models.
Only reference frames/hierarchy change; source attributes and material buffers stay.
"""
import argparse,copy,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,write_glb,mesh_instances,scene_nodes
from audit_joint_axes import audit as audit_step
from gripper_fit import section_radius,fit_angle,pad_radius
from assembly_collision import export as export_collision
C=np.array([[0.,0,1],[1,0,0],[0,1,0]]) # source PIE XYZ -> body FLU
B=C.T # FLU -> native glTF left/up/forward
BODY=np.array([-.04133,.18,.09173])
CORE_C=np.array([[0.,0,-1],[1,0,0],[0,-1,0]])
CORE_O=np.array([-.1,.041,.084])
CORE_STEP_SHA256={
    'arm-and-shared':'6ddb30a5f101299714874fd88804bacc3af0f053e7213474c88c04416e60338f',
    'pedestal-and-shoulder':'b663d87fe15b68b027ec4b2f0d80870b20b10b09bef7f3343fd7a44e104105dc',
    'tool-head':'5c3418e162978faf7029bb4f0dabcadd867e70c1a1dce88cd8ef0536034f298f'}
UNIT_STEP_SHA256='582af5cca8afa66ddf90bb8d686ff171c86dafe41318d16e31846e4392985222'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def transform(rotation,translation):
    m=np.eye(4);m[:3,:3]=rotation;m[:3,3]=translation;return m

def pose(m):
    q=Rotation.from_matrix(m[:3,:3]).as_quat();return dict(translation_m=m[:3,3].tolist(),rotation_wxyz=q[[3,0,1,2]].tolist())

# Camera harnesses protrude in the source CAD but are flexible cables, not rigid
# camera/lift structure. User-requested omission from visuals and collisions.
CAMERA_CABLE_PATHS=('1/2/6/1/1/1/1/4','1/2/6/1/1/1/1/5')


def engineer_group(path):
    if any(path==p or path.startswith(p+'/') for p in CAMERA_CABLE_PATHS):return None
    # Top-level shoulder insert shares L1's attachment origin and bearing axis.
    # User-reviewed 2026-10-19: it rotates with L1, not the fixed chassis.
    if path=='1/3' or path.startswith('1/3/'):return 'j2'
    if any(path.startswith(prefix) for prefix in ['1/1/1/10/2/','1/1/2/11/2/','1/1/3/10/2/','1/1/4/10/2/','1/2/8/1/2/']):return None
    if path.startswith('1/2/3/21/11'):return 'uwb'
    if path.startswith('1/1/63/') and path.split('/')[3] in {'2','4'}:return 'j1'
    if not path.startswith('1/2/'):return 'body'
    section=path.split('/')[2]
    if section in {'1','9','11'}:return 'j1'
    if section=='2':
        # Elbow shaft/output plate rotate with L2; bearing outer rings remain L1.
        if any(path==p or path.startswith(p+'/') for p in ['1/2/2/8/1','1/2/2/8/5','1/2/2/8/8','1/2/2/8/9','1/2/2/8/10','1/2/2/8/11']):return 'j3'
        return 'j2'
    if section=='10':return 'j3'
    if section=='5':return 'uwb'
    if section=='6':return 'camera-lift'
    if section=='3':
        part=path.split('/')[3] if len(path.split('/'))>3 else ''
        return 'j4' if part in {'3','4','5','12','15','16','20'} else 'j3'
    if section=='4':return 'j4'
    if section=='7':return 'j6' if path.split('/')[3] in {'4','5'} else 'j5'
    if section=='8':
        part=path.split('/')[3] if len(path.split('/'))>3 else ''
        if part in {'6','7','11','14'}:return 'jaw-right'
        if part in {'8','9','10','12'}:return 'jaw-left'
        return 'j6'
    raise ValueError('unclassified PIE arm occurrence '+path)


def core_arm_group(shell):
    if shell in {1,2,3,4,5,6,7,8,9,10,11,12}:return 'j1'
    if shell in {13,14,15,16,17,18,19,20,49,52}:return 'j2'
    if shell in {21,22,23,24,51}:return 'j3'
    if shell in {25,26,27,28,29,30,31,32,50}:return 'j4'
    if shell in {33,34,35,36,37,42,43,47,48}:return 'j5'
    if shell in {38,39,40,41,44,45,46}:return 'j6'
    raise ValueError('unclassified core arm shell')


def core_head_group(shell):
    if not 1<=shell<=1600:raise ValueError('unclassified core head shell')
    if shell==1223 or 1224<=shell<=1429 or 1431<=shell<=1595:return 'q'
    if shell==1430:return 'p'
    return 'j6'


def bind(document,binary,select,source_to_flu,frames,prefix):
    """Reparent source leaves without changing any geometry/material bytes."""
    d=copy.deepcopy(document);world={i:m for i,m,_ in scene_nodes(d)}
    bones={};kept=[];removed=[]
    for name,f in frames.items():
        bones[name]=len(d['nodes']);native=transform(B,np.zeros(3))@f@transform(B.T,np.zeros(3))
        d['nodes'].append(dict(name=f'link/{prefix}/{name}',matrix=native.flatten(order='F').tolist(),children=[]))
    for ni,m in world.items():
        if 'mesh' not in document['nodes'][ni]:continue
        group=select(document['nodes'][ni])
        if group is None:removed.append(ni);continue
        if group not in frames:raise ValueError('unknown rig group '+group)
        node=copy.deepcopy(document['nodes'][ni]);node.pop('children',None)
        for key in ['matrix','rotation','translation','scale']:node.pop(key,None)
        local=transform(B,np.zeros(3))@np.linalg.inv(frames[group])@source_to_flu@m
        node['matrix']=local.flatten(order='F').tolist()
        node.setdefault('extras',{}).update(assembly_group=f'{prefix}/{group}',source_node=ni)
        d['nodes'][bones[group]]['children'].append(len(d['nodes']));d['nodes'].append(node);kept.append(ni)
    d['scenes']=[dict(nodes=list(bones.values()))];d['scene']=0
    if d.get('materials',[])!=document.get('materials',[]) or d['meshes']!=document['meshes']:raise ValueError('source materials or primitives changed')
    # Every retained source mesh is present once with the same primitive/accessor.
    actual=list(mesh_instances(d,binary));expected=[v for v in mesh_instances(document,binary) if v[0] in kept]
    if sum(len(v[3]) for v in actual)!=sum(len(v[3]) for v in expected):raise ValueError('triangle coverage changed')
    maximum=0.
    source={(i,p):(v@source_to_flu[:3,:3].T+source_to_flu[:3,3]) for i,p,v,t,mat in expected}
    for ni,pi,p,t,mat in actual:
        old=d['nodes'][ni]['extras']['source_node'];reference=source[(old,pi)]
        maximum=max(maximum,float(np.abs(p@B-reference).max()))
    if maximum>1e-10:raise ValueError(f'zero-pose geometry changed: {maximum}')
    return d,binary,dict(retained_source_mesh_nodes=len(kept),removed_nodes=removed,triangles=sum(len(v[3]) for v in actual),
        maximum_reference_vertex_error_m=maximum,geometry_buffers_exact=True)


def frames_from_axes(axes):return {f'j{i+1}':transform(np.eye(3),a['origin_m']) for i,a in enumerate(axes)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);a=p.parse_args()
    source=a.sources;rows=json.loads((source/'pie-2026-tunnel-engineer-hierarchy.json').read_text());by={r['path']:r for r in rows}
    audit=json.loads(a.audit.read_text());step=source/'pie-2026-tunnel-engineer.step'
    if audit['source_sha256']!=sha(step) or sha(step)!='bfb91b499f17488ed1deb523568869f2fcb29436a53cbc39ec5e64ac4a822c47':raise ValueError('PIE STEP/audit mismatch')
    original,binary=read_glb(source/'pie-2026-tunnel-engineer-pilot/package/materials.glb')
    root=np.array(original['nodes'][0]['matrix']).reshape(4,4,order='F')
    center=np.array(json.loads((source/'pie-2026-tunnel-engineer-frame.json').read_text())['source_center_mm'])/1000
    def native_point(point):return np.asarray(point)/1000-center+root[:3,3]
    paths=['1/1/63/1','1/2/1/2','1/2/2/8/6','1/2/3/19','1/2/4/14','1/2/7/3']
    axes=[];evidence=[]
    for i,path in enumerate(paths):
        ids=by[path]['native_solids'];c=next(c for c in audit['cylinders'] if c.get('solid') in ids)
        axes.append(dict(origin_m=(C@(native_point(c['point_mm'])-BODY)).tolist(),axis=(C@np.array(c['axis'])).tolist(),
            range_rad=[-np.pi,np.pi] if i!=3 else [-np.pi/2,np.pi/2]))
        evidence.append(dict(joint=f'j{i+1}',path=path,name=by[path]['name'],occt_solid=ids,occt_face=c['face'],source_point_mm=c['point_mm'],source_axis=c['axis'],radius_mm=c['radius_mm']))
    # Grasp centre between the two TPU jaw envelopes, unit long axis along the gripper hinges.
    pads=np.array([by[v]['bounds_mm'] for v in ['1/2/8/7','1/2/8/9']]);point=(pads[:,:3].mean(0)+pads[:,3:].mean(0))/2
    jaw_c=next(c for c in audit['cylinders'] if c.get('solid')==1670)
    z=C@np.array(jaw_c['axis']);x=np.array(axes[-1]['axis']);x-=z*np.dot(x,z);x/=np.linalg.norm(x);y=np.cross(z,x)
    tool=transform(np.column_stack([x,y,z]),C@(native_point(point)-BODY))
    engineer=dict(axes=axes,tool=pose(tool));frames=frames_from_axes(axes);frames['body']=np.eye(4)
    jaws=[]
    for name,sid,sign in [('jaw-left',1671,-1),('jaw-right',1670,1)]:
        c=next(c for c in audit['cylinders'] if c.get('solid')==sid)
        origin=C@(native_point(c['point_mm'])-BODY);axis=C@np.array(c['axis']);frames[name]=transform(np.eye(3),origin)
        jaws.append(dict(name=name,origin_m=origin.tolist(),axis=axis.tolist(),open_rad=sign*0.55))
    auxiliary=[]
    for name,pivot,translation,axis,angle in [
        ('camera-lift',[.07906,.27503,.02971],[0,-.0494975,-.0494975],[0,1,0],0.),
        ('uwb',[.07083,.22038,-.06684],[0,0,0],[.0284937,0,.999594],-np.deg2rad(20))]:
        origin=C@(np.array(pivot)-BODY);direction=C@np.array(axis);direction/=np.linalg.norm(direction)
        rotation=Rotation.from_rotvec(direction*angle).as_matrix()
        change=transform(rotation,origin-rotation@origin+C@np.array(translation))
        frames[name]=transform(np.eye(3),origin)
        auxiliary.append(dict(name=name,reference=pose(frames[name]),stowed_delta=pose(change)))
    owners={sid:r['path'] for r in rows for sid in r.get('native_solids',[])}
    def select(n):
        e=n.get('extras',{});return engineer_group(e.get('source_leaf_path') or owners.get(e.get('native_solid_index'),''))
    a.out.mkdir(parents=True,exist_ok=True);files={};reports={}
    def output(name,doc,b,selector,conversion,frames,prefix):
        d,payload,report=bind(doc,b,selector,conversion,frames,prefix);target=a.out/(name+'.glb');write_glb(target,d,payload)
        _,written=read_glb(target)
        if written!=b:raise ValueError('written geometry payload changed')
        files[name]=dict(file=target.name,sha256=sha(target));reports[name]=report
    # Fail closed if a different source assembly invalidates the reviewed mount.
    insert_placement=np.array(by['1/3']['placement'])
    plate_placement=np.array(by['1/2/2/3']['placement'])
    ownership_error=float(np.linalg.norm(insert_placement[:,3]-plate_placement[:,3]))
    bearing_alignment=float(abs(insert_placement[:,2]@plate_placement[:,2]))
    # Its local frame is clocked 180 degrees relative to the plate; the bearing
    # line is identical, with opposite axis signs. Do not require identical frames.
    if ownership_error>1e-8 or bearing_alignment<1-1e-12:raise ValueError('shoulder insert/L1 attachment mismatch')
    output('engineer',original,binary,select,transform(C,-C@BODY),frames,'engineer')
    reports['engineer']['omitted_cable_assemblies']=[dict(path=path,
        source_solids=sorted(sid for row in rows if row['path']==path or row['path'].startswith(path+'/') for sid in row.get('native_solids',[])),
        reason='User-requested removal of protruding flexible camera wires and connector ends from visuals and collision geometry.') for path in CAMERA_CABLE_PATHS]
    reports['engineer']['ownership_overrides']=[dict(path='1/3',owner='j2',
        source_placement_reference='1/2/2/3',attachment_origin_difference_mm=ownership_error,bearing_axis_abs_dot=bearing_alignment,
        reason='User-reviewed shoulder insert moves with L1; formerly frozen in chassis group. Geometry preserved.')]
    # RMUC2027 core: actual six UR-style positioning bearings. Points on each axis
    # are arbitrary gauges; they need not be at bearing-envelope centres.
    core_audits={}
    for part in ['arm-and-shared','tool-head']:
        path=ROOT/f'out/rmuc2027-equipment-pipeline/technology-core/{part}/source.step'
        saved=a.out/('audit-core-'+part+'.json')
        data=json.loads(saved.read_text()) if saved.exists() else None
        if data is None or data['source_sha256']!=sha(path):
            data=audit_step(path);saved.write_text(json.dumps(data,indent=2)+'\n')
        core_audits[part]=data
    def cylinder(part,shell,radius):
        cs=[c for c in core_audits[part]['cylinders'] if c['shell']==shell]
        return min(cs,key=lambda c:abs(c['radius_mm']-radius))
    core_axes=[];core_evidence=[]
    for shell,radius in [(2,76),(18,78.5),(52,58.5),(51,44.5),(50,38),(47,39)]:
        c=cylinder('arm-and-shared',shell,radius);v=CORE_C@np.array(c['axis']);v/=np.linalg.norm(v)
        core_axes.append(dict(origin_m=(CORE_C@(np.array(c['point_mm'])/1000-CORE_O)).tolist(),axis=v.tolist(),range_rad=[-np.pi,np.pi]))
        core_evidence.append(c)
    # Figure 5-7: Q follows the front shaft; P is the cam's transverse axis.
    post=cylinder('tool-head',1224,18)
    # Fig 5-7/5-15: Q is the carriage's vertical spindle BEFORE the P flip,
    # not the insertion post. Its axis becomes panel-normal after the P flip.
    qc=cylinder('tool-head',1430,11.75)
    q_origin=np.array(post['point_mm'])/1000;q_axis=-np.array(post['axis']);q_axis/=np.linalg.norm(q_axis)
    tangent=np.cross([0,-1,0],q_axis);tangent/=np.linalg.norm(tangent)
    socket=transform(np.column_stack([q_axis,tangent,np.cross(q_axis,tangent)]),q_origin+q_axis*.1)
    socket_flu=transform(CORE_C,-CORE_C@CORE_O)@socket
    core=dict(axes=core_axes,tool=pose(socket_flu));core_frames=frames_from_axes(core_axes);core_frames['body']=np.eye(4)
    lift=CORE_C@(q_origin-CORE_O)
    # Figure 5-7 (2026 EN p82 and 2027 CN p79-80): P is 208 mm above
    # the initial post centreline, 15 mm ahead of the panel. The tip reaches
    # 169 mm from that panel. These dimensions imply the 54/15 mm final offsets.
    # A small transverse fastener is NOT this pivot.
    normal=socket_flu[:3,0];up=socket_flu[:3,2]
    p_origin=socket_flu[:3,3]-(.169-.015)*normal+.208*up
    p_axis=-socket_flu[:3,1]
    core_frames.update(lift=transform(np.eye(3),lift),p=transform(np.eye(3),p_origin),q=transform(np.eye(3),CORE_C@(np.array(qc['point_mm'])/1000-CORE_O)))
    inputs={}
    for part,file in [('arm-and-shared','core-arm'),('pedestal-and-shoulder','core-base'),('tool-head','core-head')]:
        base=ROOT/f'out/rmuc2027-equipment-pipeline/technology-core/{part}';meta=json.loads((base/'native.json').read_text())
        if sha(base/'source.step')!=CORE_STEP_SHA256[part] or meta['source_step_sha256']!=CORE_STEP_SHA256[part] or sha(base/'native.glb')!=meta['native_glb_sha256']:raise ValueError('core native input mismatch')
        d,b=read_glb(base/'native.glb');inputs[part]=dict(step_sha256=sha(base/'source.step'),glb_sha256=sha(base/'native.glb'))
        def classify(n,part=part):
            index=n['extras']['native_shell_index']
            if part=='arm-and-shared':return core_arm_group(index)
            return core_head_group(index) if part=='tool-head' else 'body'
        output(file,d,b,classify,transform(CORE_C,-CORE_C@CORE_O),core_frames,'core')
    unit=ROOT/'out/rmuc2027-equipment-pipeline/energy-unit/unit/native.glb'
    unit_meta=json.loads(unit.with_name('native.json').read_text())
    if sha(unit)!=unit_meta['native_glb_sha256'] or sha(unit.with_name('source.step'))!=UNIT_STEP_SHA256 or unit_meta['source_step_sha256']!=UNIT_STEP_SHA256:raise ValueError('Energy Unit input mismatch')
    d,b=read_glb(unit)
    unit_c=np.array([[1.,0,0],[0,0,-1],[0,1,0]])
    output('unit',d,b,lambda n:'unit',transform(unit_c,np.array([0,0,-.075])),{'unit':np.eye(4)},'unit')
    # OXYZ: midpoint of the pedestal's front floor edge; +X follows the
    # reference post normal. Fit the rectangular footprint, excluding shoulder.
    base_doc,base_bin=read_glb(ROOT/'out/rmuc2027-equipment-pipeline/technology-core/pedestal-and-shoulder/native.glb')
    base_points=np.concatenate([v for _,_,v,_,_ in mesh_instances(base_doc,base_bin)])
    base_flu=(base_points-CORE_O)@CORE_C.T
    floor=base_flu[base_flu[:,2]<base_flu[:,2].min()+1e-5]
    front=floor[np.abs(floor[:,0]-floor[:,0].max())<1e-5]
    o=np.array([front[:,0].max(),(front[:,1].min()+front[:,1].max())/2,0.])
    head_doc,head_bin=read_glb(ROOT/'out/rmuc2027-equipment-pipeline/technology-core/tool-head/native.glb')
    head_points=np.concatenate([v for _,_,v,_,_ in mesh_instances(head_doc,head_bin)])
    head_flu=(head_points-CORE_O)@CORE_C.T
    envelope=head_flu[ConvexHull(head_flu).vertices]
    # The 95 mm caps do not describe the mid-body grasp: section the actual
    # source triangles at the two TPU-pad heights (the body is about 64.6 mm).
    ud,ub=read_glb(a.out/'unit.glb')
    unit_triangles=np.concatenate([v[t] for _,_,v,t,_ in mesh_instances(ud,ub)])@B
    radius=section_radius(unit_triangles,[-.011,0.,.011])
    ed,eb=read_glb(a.out/'engineer.glb');pad_parts={}
    for ni,_,v,t,_ in mesh_instances(ed,eb):
        paths=ed['nodes'][ni]['extras'].get('source_occurrence_paths',[])
        if any(path in {'1/2/8/7','1/2/8/9'} for path in paths):
            name=ed['nodes'][ni]['extras']['assembly_group'].split('/')[-1]
            pad_parts.setdefault(name,[]).append(((v@B-tool[:3,3])@tool[:3,:3])[t])
    for jaw in jaws:
        triangles=np.concatenate(pad_parts[jaw['name']]);pivot=(np.array(jaw['origin_m'])-tool[:3,3])@tool[:3,:3]
        jaw['closed_rad']=fit_angle(triangles,pivot,jaw['open_rad'],radius+.0001)
        jaw['pad_contact_radius_m']=pad_radius(triangles,pivot,jaw['closed_rad'])
    config=dict(schema=5,engineer_auxiliary=auxiliary,assembly_frame=pose(transform(np.eye(3),o)),core_envelope_m=envelope.tolist(),
        engineer=engineer,engineer_jaws=jaws,grasp=dict(unit_body_radius_m=radius,clearance_m=.0001,pad_paths=['1/2/8/7','1/2/8/9'],method='source-triangle-sections-and-pad-sweep-v1'),core=core,core_p_origin_m=p_origin.tolist(),
        core_p_axis=p_axis.tolist(),core_q_origin_m=(CORE_C@(np.array(qc['point_mm'])/1000-CORE_O)).tolist(),
        core_q_axis=(-CORE_C@np.array(qc['axis'])).tolist(),core_lift_axis=[0,0,1],engineer_bearings=evidence,
        core_bearings=core_evidence,core_p_calibration=dict(method='rulebook-figure-5-7',reference='2026 EN V2.1.0 p82; 2027 CN V1.0.0 Fig5-7',height_above_post_m=.208,post_reach_from_panel_m=.169,hinge_offset_from_panel_m=.015),core_q_bearing=qc,core_post_bearing=post,core_inputs=inputs,unit_source_sha256=sha(unit),source_step_sha256=audit['source_sha256'],
        policy='Source-preserved CAD rig. Joint ranges are numerical workbench guards; PIE J4 report describes about 180 degrees. Jaw opening, core bearing gauges and rigid ownership require visual review. P is fitted from Figure 5-7 dimensions (208/169/15 mm), not inferred from a small fastener; Q follows the 11.75 mm carriage spindle as a kinematic hypothesis. OXYZ +X is the reference post outward direction and O is the front floor-edge midpoint. No self-collision, torque or force calibration; P/Q and carriage groups are source-based hypotheses, not certified sensor geometry.')
    cfg=a.out/'assembly.json';cfg.write_text(json.dumps(config,indent=2)+'\n');files['config']=dict(file=cfg.name,sha256=sha(cfg))
    files['collision']=export_collision(a.out)
    source_meta=json.loads(Path(__file__).with_name('candidates.json').read_text())['sources']['tunnel_heavy']
    notice=source_meta['credit']+'\n'+source_meta['source_article']+'\n'+source_meta['terms']+'\n\nDJI RoboMaster RMUC2027 V1.0.0 Technology Core and Energy Unit; upstream ownership retained.\n'+config['policy']+'\n'
    (a.out/'CAD-NOTICE.md').write_text(notice)
    (a.out/'manifest.json').write_text(json.dumps(dict(schema=1,profile='pie-rmuc2027-assembly-workbench-v5',files=files,reports=reports,
        source_step_sha256=audit['source_sha256'],input_mesh_sha256=sha(source/'pie-2026-tunnel-engineer-pilot/package/materials.glb'),input_hierarchy_sha256=sha(source/'pie-2026-tunnel-engineer-hierarchy.json'),audit_sha256=sha(a.audit),producer_sha256=sha(__file__),source_field_sha256='a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0'),indent=2)+'\n')
    print(json.dumps(reports,indent=2))

if __name__=='__main__':main()
