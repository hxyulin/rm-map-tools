"""Explicit arm-cylinder collision study with paired open tube profiles.

Starts at installed reference, never changes a protected head or installed file.
Solid joint collision intentionally fills housing cavities, unlike the visuals.
"""
import copy,importlib.util,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'benchmarks/2026-10-23-box-primitive-candidates')]
import scan
from gltf_scene import read_glb,write_glb,accessor,scene_nodes
from simplify_package import append_accessor,compact,scene_triangles
from collision_shape_export import export as export_native
from mesh_quality import distances
OUT=ROOT/'out/rmuc2027-core-arm-proxies'

def module(name,path):
    s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
import glb_proxy_review as pair

def basis(a):
    a=np.asarray(a,float);a/=np.linalg.norm(a);u=np.cross(a,[1.,.123,.456]);u/=np.linalg.norm(u)
    return a,u,np.cross(a,u)

def revolve(c,a,profile,segments=32):
    a,u,v=basis(a);angle=np.arange(segments)*2*np.pi/segments
    radial=np.cos(angle)[:,None]*u+np.sin(angle)[:,None]*v
    p=np.concatenate([c+z*a+r*radial for z,r in profile]);t=[]
    for j in range(len(profile)-1):
        for i in range(segments):
            b=j*segments+i;n=j*segments+(i+1)%segments
            t.extend([[b,n,b+segments],[n,n+segments,b+segments]])
    g=p[np.array(t)]
    # tangent cross axial points outward; endpoint annuli follow the same winding.
    return g

def cylinder(s,segments=24):
    c=np.array(s['center_m'])*1000;a=np.array(s['axis_unit_vector']);r=s['radius_m']*1000;h=s['length_m']*500
    # Circumscribed diagnostic, so native round cylinder is contained in preview.
    r/=np.cos(np.pi/segments);g=revolve(c,a,[[-h,r],[h,r]],segments)
    a,u,v=basis(a);theta=np.arange(segments)*2*np.pi/segments;rad=r*(np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v)
    caps=[]
    for sign in [-1,1]:
        cap=c+sign*h*a;ring=cap+rad
        for i in range(segments):
            t=np.array([cap,ring[i],ring[(i+1)%segments]])
            caps.append(t if sign>0 else t[::-1])
    return np.concatenate([g,np.array(caps)])

def shape(c,a,r,length):
    a=np.asarray(a,float);a/=np.linalg.norm(a)
    return dict(center_m=(np.asarray(c)/1000).tolist(),axis_unit_vector=a.tolist(),radius_m=float(r/1000),length_m=float(length/1000),solid=True)

def fit_shape(row):return shape(row['center_mm'],row['axis'],row['radius_mm'],row['length_mm'])

def extend_to_bounds(s,g,radius=None):
    s=copy.deepcopy(s);c=np.array(s['center_m'])*1000;a=np.array(s['axis_unit_vector']);z=(g.reshape(-1,3)-c)@a
    return shape(c+a*(z.min()+z.max())/2,a,radius if radius is not None else s['radius_m']*1000,np.ptp(z))

def tube_branch(main,tube_axis,tube_center,tube_end_z,radius):
    a=np.array(tube_axis);c=np.array(tube_center);end=c+tube_end_z*a
    # Axis intersection with the main barrel line determines the hidden endpoint.
    mc=np.array(main['center_m'])*1000;ma=np.array(main['axis_unit_vector'])
    t=np.linalg.lstsq(np.column_stack([a,-ma]),mc-c,rcond=None)[0][0]
    joint=c+t*a;return shape((end+joint)/2,a,radius,np.linalg.norm(end-joint))

def smooth_profile_normals(g,c,a,profile,segments=32):
    a=np.asarray(a,float);values=[]
    for j,((z0,r0),(z1,r1))in enumerate(zip(profile[:-1],profile[1:])):
        band=g[j*segments*2:(j+1)*segments*2]
        q=band-np.asarray(c);rad=q-(q@a)[:,:,None]*a;rad/=np.linalg.norm(rad,axis=2)[:,:,None]
        n=(z1-z0)*rad-(r1-r0)*a;n/=np.linalg.norm(n,axis=2)[:,:,None];values.append(n)
    return np.concatenate(values)

def replace(source,target,replacements,smooth=None):
    d,b=read_glb(source);a=copy.deepcopy(d);binary=bytearray(b);world={i:w for i,w,_ in scene_nodes(d)}
    for ni,g in replacements.items():
        old=d['meshes'][d['nodes'][ni]['mesh']];assert len(old['primitives'])==1
        # Every owner remains in its original hierarchy; convert scene geometry back.
        w=world[ni];inv=np.linalg.inv(w);local=(g*.001)@inv[:3,:3].T+inv[:3,3]
        new=copy.deepcopy(old);pr=pair.primitive(a,binary,local*1000,old['primitives'][0])
        if smooth and ni in smooth:
            normals=smooth[ni]@w[:3,:3];normals/=np.linalg.norm(normals,axis=2)[:,:,None]
            pr['attributes']['NORMAL']=append_accessor(a,binary,normals.reshape(-1,3).astype(np.float32),'VEC3',5126)
        new['primitives']=[pr]
        a['nodes'][ni]['mesh']=len(a['meshes']);a['meshes'].append(new)
    write_glb(target,a,compact(a,binary))
    return dict(unchanged_mesh_owners=pair.unchanged(source,target,set(replacements)),before=scene_triangles(d),after=scene_triangles(read_glb(target)[0]),sha256=scan.digest(target))

def probes(g,n=15000):return np.concatenate([g.reshape(-1,3),g.mean(1),(g[:,0]+g[:,1])/2,(g[:,1]+g[:,2])/2,(g[:,2]+g[:,0])/2,scan.area_samples(g,n,seed=751)])

def surface(a,b):
    vals=distances(probes(a),b.reshape(-1,3),np.arange(len(b)*3).reshape(-1,3))
    return dict(max_mm=float(vals.max()),p99_mm=float(np.quantile(vals,.99)),samples=len(vals))

def solid_dist(p,shapes):
    vals=[]
    for s in shapes:
        a=np.array(s['axis_unit_vector']);q=p-np.array(s['center_m'])*1000;z=q@a
        r=np.linalg.norm(q-z[:,None]*a,axis=1);dd=np.column_stack([r-s['radius_m']*1000,abs(z)-s['length_m']*500])
        vals.append(np.linalg.norm(np.maximum(dd,0),axis=1)+np.minimum(dd.max(1),0))
    return np.min(vals,axis=0)

def main():
    OUT.mkdir(exist_ok=True);ref=json.loads(scan.REF.read_text());sources={role:Path(ref['roles'][role]['assets']['tech-core']['path'])for role in ['visual','collision']}
    for role,p in sources.items():assert scan.digest(p)==ref['roles'][role]['assets']['tech-core']['sha256']
    cd,cc,cn=scan.load_nodes(sources['collision']);vd,vc,vn=scan.load_nodes(sources['visual'])
    fit=json.loads((OUT/'circle-research.json').read_text());assert scan.digest(sources['collision'])==fit['sha256']
    # Explicit reviewed source identities, never a spatial match between unrelated nodes.
    mapping={17:15,26:24};tube_geos={};tube_rows=[];tube_axes={};smooth={}
    profiles={17:[[-381.23149,57.7],[-380.93144,58],[65.92,58.143],[70.57,59.278],[78.41,64.633],[82.9,73],[86.97,76],[100.7686,76],[100.7686,72.5]],
        26:[[-238.73,41.5],[-238.73,43.5],[-230.42,43.5],[-225.9,40.4],[-223.88,39.5],[225.57,39.5],[229.5,42.4],[232.57,43.5],[244.38,43.5],[244.38,41.5]]}
    for ni,vi in mapping.items():
        assert cd['nodes'][ni]['name']==vd['nodes'][vi]['name'];assert cc[ni]==vc[vi]=='technology-core/arm-and-shared'
        axis_path=ROOT/f'out/rmuc2027-core-collision-manual/axis-{ni}.npz';x=np.load(axis_path);c=x['center'];axis=x['axis'];tube_axes[ni]=(c,axis)
        g=revolve(c,axis,profiles[ni]);tube_geos[ni]=g;smooth[mapping[ni]]=smooth_profile_normals(g,c,axis,profiles[ni])
        forward=surface(cn[ni],g);reverse=surface(g,cn[ni]);assert max(forward['max_mm'],reverse['max_mm'])<2.0
        tube_rows.append(dict(collision_node=ni,visual_node=vi,source_name=cd['nodes'][ni]['name'],profile_mm=profiles[ni],segments=32,
            center_mm=c.tolist(),axis=axis.tolist(),source_collision_triangles=len(cn[ni]),source_visual_triangles=len(vn[vi]),candidate_triangles=len(g),
            source_to_candidate=forward,candidate_to_source=reverse,axis_evidence=str(axis_path),axis_evidence_sha256=scan.digest(axis_path),
            deliberate_losses='Fine fillet/chamfer and groove sections omitted; full open endpoints, main flare and collars retained.'))
    joints={}
    # Large shoulder: perpendicular barrel and arm-facing cylindrical branch.
    joints[5]=[extend_to_bounds(fit_shape(fit['nodes']['5'][0][0]),cn[5],76),fit_shape(fit['nodes']['5'][1][0])]
    # Upper elbow: reuse the previously reviewed three-cylinder reconstruction.
    previous=ROOT/'rules/collision-shapes-tech-core-compound-trial.json'
    joints[22]=json.loads(previous.read_text())['replacements'][0]['cylinders']
    # Lower elbow and wrist retain source-supported cross-barrel and tube branch axes.
    for ni,ti,end,radius in [(18,17,-381.23149,58),(25,26,-238.73,43.5)]:
        main=extend_to_bounds(fit_shape(fit['nodes'][str(ni)][1][0]),cn[ni],radius)
        c,a=tube_axes[ti];joints[ni]=[main,tube_branch(main,a,c,end,radius)]
    replacements=dict(tube_geos);joint_rows=[]
    for ni,shapes in joints.items():
        assert cc[ni]=='technology-core/arm-and-shared'
        proxy=np.concatenate([cylinder(s)for s in shapes]);replacements[ni]=proxy
        outside=solid_dist(probes(cn[ni]),shapes)
        reverse=surface(proxy,cn[ni])
        joint_rows.append(dict(node=ni,name=cd['nodes'][ni]['name'],source_triangles=len(cn[ni]),diagnostic_triangles=len(proxy),
            cylinders=shapes,source_samples_outside_native_union_max_mm=float(max(0,outside.max())),source_samples_outside_over_3mm=int((outside>3).sum()),
            diagnostic_surface_to_source=reverse,intentional_loss='Solid cylinders fill the joint bore, side access openings, and enclosed hardware; narrow flange/groove details omitted.',
            status='manual_collision_trial_not_contact_qualified'))
    visual_target=OUT/'visual-tech-core.glb';collision_target=OUT/'collision-tech-core.glb'
    vcheck=replace(sources['visual'],visual_target,{mapping[i]:g for i,g in tube_geos.items()},smooth);ccheck=replace(sources['collision'],collision_target,replacements)
    vactual=scan.load_nodes(visual_target)[2];cactual=scan.load_nodes(collision_target)[2]
    for ni,vi in mapping.items():assert np.array_equal(vactual[vi],cactual[ni])
    # Export real parameter cylinders, rather than counting preview tessellation as native.
    # The native contract's source includes paired tube edits, so retained arrays are exact.
    intermediate=OUT/'tube-profile-collision.glb';replace(sources['collision'],intermediate,tube_geos)
    intermediate_doc,_=read_glb(intermediate);world={i:w for i,w,_ in scene_nodes(intermediate_doc)};selections=[]
    for ni,shapes in joints.items():
        assert np.array_equal(world[ni],np.eye(4)), 'source-scene cylinder parameters require identity owner mount here'
        selections.append(dict(node_index=ni,node_name=cd['nodes'][ni]['name'],cylinders=shapes,review_status='arm-manual-prototype-not-contact-approved'))
    selection=dict(source_sha256=scan.digest(intermediate),asset_id='tech-core',replacements=selections)
    (OUT/'native-selection.json').write_text(json.dumps(selection,indent=2)+'\n');native=export_native(intermediate,selection,OUT/'native')
    pins={str(p):scan.digest(p)for p in sources.values()};pins[str(previous)]=scan.digest(previous)
    for row in tube_rows:pins[row['axis_evidence']]=row['axis_evidence_sha256']
    for p,h in ref['pins'].items():assert scan.digest(Path(p))==h;pins[p]=h
    baseline=json.loads((ROOT/'out/rmuc2027-paired-column-visual/paired-stage.json').read_text())
    stage=copy.deepcopy(baseline)
    for role,target,check in [('visual',visual_target,vcheck),('collision',collision_target,ccheck)]:
        stage[f'{role}_assets']['tech-core']=dict(path=str(target),sha256=scan.digest(target),triangles=check['after'],placements=2,placed_triangles=check['after']*2)
    # Preserve the previous review as an immutable reference.
    totals={role:sum(x['placed_triangles']for x in stage[f'{role}_assets'].values())for role in ['visual','collision']}
    stage.update(variant='arm-tubes-and-four-joints-trial',status='Core arm review trial over accepted Outpost pair; not installed or contact qualified',placed_visual_triangles=totals['visual'],placed_collision_triangles=totals['collision'],installed=False,contact_validated=False)
    (OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
    result=dict(sources={role:str(p)for role,p in sources.items()},visual_candidate=str(visual_target),collision_candidate=str(collision_target),visual=vcheck,collision=ccheck,
        tubes=tube_rows,joints=joint_rows,placed_visual_saved=2*(vcheck['before']-vcheck['after']),placed_collision_saved=2*(ccheck['before']-ccheck['after']),
        field_visual_triangles=totals['visual'],field_collision_preview_triangles=totals['collision'],native_mesh_triangles_per_core=native['retained_mesh']['triangles'],
        native_cylinders_per_core=len(native['native_parts']),native_removed_joint_mesh_triangles_per_core=native['removed_mesh_triangles'],
        previous_pair_stage=str(ROOT/'out/rmuc2027-paired-column-visual/paired-stage.json'),
        protected_visual_nodes=[i for i in vn if vc[i]!='technology-core/arm-and-shared'],
        source_arm_collision_triangles_per_core=sum(len(g)for i,g in cn.items()if cc[i]=='technology-core/arm-and-shared'),
        candidate_arm_collision_triangles_per_core=sum(len(g)for i,g in cactual.items()if cc[i]=='technology-core/arm-and-shared'),
        input_pins=pins,installed=False,contact_validated=False,
        limits=['Joint visuals deliberately retain their detailed hollow shells; solid collision cylinders are different representations.',
            'Finite exterior/contact checks, not continuous or all-pose clearance proof. Joint bores/access holes are blocked in collision.',
            'Diagnostic cylinder previews circumscribe the true native round cylinders; native totals must not count preview triangles.',
            'Other small hardware and two more complex motor housings remain untouched. No FPS improvement measured.'])
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k]for k in ['placed_visual_saved','placed_collision_saved','native_cylinders_per_core','native_mesh_triangles_per_core','field_visual_triangles','field_collision_preview_triangles']}),flush=True)
    print('joint outside mm',[(r['node'],r['source_samples_outside_native_union_max_mm'])for r in joint_rows],flush=True)

if __name__=='__main__':main()
