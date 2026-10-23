"""Bounded installed rigid-node rounded primitive investigation, never an installer.

Run from any cwd with ocpenv/bin/python. All dimensions in metres unless suffixed.
No random sampling. PCA only proposes axes; acceptance uses actual surface samples.
"""
import sys, json, hashlib, argparse
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares, minimize
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'out/rmuc2027-rounded-primitive-candidates'
sys.path.insert(0, str(ROOT / 'python'))
from gltf_scene import read_glb, scene_nodes, mesh_instances
from mesh_quality import distances

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def frame(axis):
    axis = axis / np.linalg.norm(axis)
    u = np.cross(axis, np.eye(3)[np.argmin(abs(axis))]); u /= np.linalg.norm(u)
    return np.column_stack([u, np.cross(axis, u), axis])

def sdf(p, shape):
    q = (p - shape['center_m']) @ np.asarray(shape['frame'])
    r = shape['radius_m']
    if shape['kind'] == 'sphere':
        return np.linalg.norm(q, axis=1) - r
    if shape['kind'] == 'capsule':
        q[:, 2] -= np.clip(q[:, 2], -shape['segment_length_m']/2, shape['segment_length_m']/2)
        return np.linalg.norm(q, axis=1) - r
    d = np.column_stack([np.linalg.norm(q[:, :2], axis=1)-r, abs(q[:, 2])-shape['length_m']/2])
    return np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(axis=1), 0)

def surface(shape, n=96, rings=25):
    """Exact analytic surface samples; tagged flat caps, side or hemispheres."""
    a = np.arange(n) * (2*np.pi/n)
    circle = np.column_stack([np.cos(a), np.sin(a)])
    r = shape['radius_m']; points = []; tags = []
    def ring(rad, z, tag):
        points.extend(np.column_stack([circle*rad, np.full(n,z)])); tags.extend([tag]*n)
    kind = shape['kind']
    if kind == 'cylinder':
        h = shape['length_m']/2
        for z in np.linspace(-h,h,rings): ring(r,z,'side')
        for sign in [-1,1]:
            for rad in np.linspace(0,r,13): ring(rad,sign*h,'cap')
    else:
        h = shape.get('segment_length_m',0)/2
        if h:
            for z in np.linspace(-h,h,rings): ring(r,z,'side')
        for sign in [-1,1]:
            for t in np.linspace(0,np.pi/2,rings): ring(r*np.cos(t),sign*(h+r*np.sin(t)),'hemisphere')
    return np.asarray(points) @ np.asarray(shape['frame']).T + shape['center_m'], np.asarray(tags)

def diagnostic_mesh(shape, n=96):
    # Ring triangulation used only for diagnostic rendering, never native export.
    r=shape['radius_m']; rows=[]
    if shape['kind']=='cylinder':
        h=shape['length_m']/2; rows=[(0,-h),(r,-h),(r,h),(0,h)]
    else:
        h=shape.get('segment_length_m',0)/2
        for t in np.linspace(-np.pi/2,0,17): rows.append((r*np.cos(t),-h+r*np.sin(t)))
        for t in np.linspace(0,np.pi/2,17): rows.append((r*np.cos(t),h+r*np.sin(t)))
    a=np.arange(n)*2*np.pi/n
    p=np.vstack([np.column_stack([rad*np.cos(a),rad*np.sin(a),np.full(n,z)]) for rad,z in rows])
    t=[]
    for j in range(len(rows)-1):
        for i in range(n):
            a0=j*n+i; b=j*n+(i+1)%n; c=b+n; d=a0+n
            t.extend([[a0,b,c],[a0,c,d]])
    return p@np.asarray(shape['frame']).T+shape['center_m'],np.asarray(t)

def samples(p,t):
    q=p[t]
    return np.vstack([p,q.mean(axis=1),(q[:,0]+q[:,1])/2,(q[:,1]+q[:,2])/2,(q[:,2]+q[:,0])/2])

def axes(p,t):
    _,_,v=np.linalg.svd(p-p.mean(axis=0),full_matrices=False)
    q=p[t]; normals=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]); area=np.linalg.norm(normals,axis=1)
    candidates=list(v)
    # Area-ranked actual planar normals and normal covariance recover cylinder axes
    # even when angular/axial tessellation makes vertex PCA biased.
    good=area>1e-16; normals=normals[good]/area[good,None]; area=area[good]
    _,e=np.linalg.eigh((normals*area[:,None]).T@normals)
    candidates.extend(e.T)
    candidates.extend(normals[np.argsort(-area)[:24]])
    result=[]
    for a in candidates:
        if not any(abs(a@b)>.9999 for b in result): result.append(a)
        if len(result)==10: break
    return result

def propose(p,t):
    origin=(p.min(axis=0)+p.max(axis=0))/2; size=np.ptp(p,axis=0).max()
    x=(p-origin)/size
    # Sphere nonlinear surface fit. No enclosing-volume assumption.
    fit=least_squares(lambda v:np.linalg.norm(x-v[:3],axis=1)-v[3], [0,0,0,.5],max_nfev=90)
    result=[dict(kind='sphere',center_m=origin+size*fit.x[:3],frame=np.eye(3),radius_m=abs(size*fit.x[3]))]
    for a in axes(p,t):
        f=frame(a); q=x@f
        c0=(q[:,:2].min(axis=0)+q[:,:2].max(axis=0))/2
        # Minimax enclosing circular section, not a radial percentile.
        fit=minimize(lambda c:np.max(np.sum((q[:,:2]-c)**2,axis=1)),c0,method='Nelder-Mead',options={'maxiter':100,'xatol':1e-8})
        c=fit.x; radius=np.linalg.norm(q[:,:2]-c,axis=1).max(); lo,hi=q[:,2].min(),q[:,2].max()
        center=origin+size*(np.r_[c,(lo+hi)/2]@f.T)
        result.append(dict(kind='cylinder',center_m=center,frame=f,radius_m=radius*size,length_m=(hi-lo)*size))
        # Capsule: explicit hemispherical ends; fitted radius, center and segment.
        def residual(v):
            d=q-np.r_[v[:2],v[2]]
            d[:,2]-=np.clip(d[:,2],-v[4]/2,v[4]/2)
            return np.linalg.norm(d,axis=1)-v[3]
        fit=least_squares(residual,[*c,(lo+hi)/2,radius,max(hi-lo-2*radius,.00001)],bounds=([-2,-2,-2,.000001,0],[2,2,2,3,5]),max_nfev=60)
        v=fit.x
        result.append(dict(kind='capsule',center_m=origin+size*(v[:3]@f.T),frame=f,radius_m=v[3]*size,segment_length_m=v[4]*size))
    return result

def stats(d,span):
    return dict(samples=len(d),max_mm=float(d.max()*1000),p99_mm=float(np.percentile(d,99)*1000),max_fraction_span=float(d.max()/span))

def cheap_roundness(p):
    """Screen only: bbox-centered cylinder/PCA residual; never final evidence."""
    x=p-(p.min(axis=0)+p.max(axis=0))/2
    _,_,v=np.linalg.svd(x,full_matrices=False)
    best=np.inf
    for a in v:
        q=x@frame(a); c=(q.min(axis=0)+q.max(axis=0))/2; q-=c
        r=np.linalg.norm(q[:,:2],axis=1).max(); h=abs(q[:,2]).max()
        d=np.minimum(abs(np.linalg.norm(q[:,:2],axis=1)-r),abs(abs(q[:,2])-h))
        best=min(best,float(np.percentile(d,95)))
    return best

def evaluate(p,t,sh,full=True):
    s=samples(p,t) if full else p
    span=float(np.ptp(p,axis=0).max())
    sd=sdf(s,sh); rev,tags=surface(sh,96 if full else 24,25 if full else 7)
    rd=distances(rev,p,t)
    result=dict(forward_outside_solid=stats(np.maximum(sd,0),span),forward_absolute_surface=stats(abs(sd),span),reverse_surface=stats(rd,span))
    result['source_inside_solid_over_1mm']=int(np.sum(sd<-.001))
    result['source_inside_depth_max_mm']=float(max(0,-sd.min())*1000)
    for tag in np.unique(tags): result['reverse_'+tag]=stats(rd[tags==tag],span)
    result['score_mm']=max(result['forward_outside_solid']['max_mm'],result['reverse_surface']['max_mm'])
    return result

def serial(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,np.generic): return x.item()
    raise TypeError(type(x).__name__)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--top',type=int,default=24)
    parser.add_argument('--resume',action='store_true',help='reuse completed node evaluations from scan.json')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    refpath=ROOT/'out/rmuc2027-installed-reference-review/review.json'; review=json.loads(refpath.read_text())
    rows=[]; coverage=[]; old={}
    if args.resume and (OUT/'scan.json').exists():
        for row in json.loads((OUT/'scan.json').read_text())['candidates']: old[(row['asset'],row['node'])]=row
    for asset,meta in sorted(review['roles']['collision']['assets'].items(),key=lambda x:x[0]!='tech-core'):
        path=ROOT/'out/rmuc2027-installed-reference-review/reference/collision'/f'{asset}.glb'
        assert sha(path)==meta['sha256']
        doc,blob=read_glb(path); grouped={}; ancestry={}; components={}; transforms={}
        for i,w,parent in scene_nodes(doc):
            ancestry[i]=ancestry.get(parent,[])+[i]; transforms[i]=w
            components[i]=doc['nodes'][i].get('extras',{}).get('component_id',components.get(parent,asset))
        for i,pi,p,t,mat in mesh_instances(doc,blob): grouped.setdefault(i,[]).append((p,t))
        meshes={}
        for i,parts in grouped.items():
            offsets=np.cumsum([0]+[len(p) for p,t in parts[:-1]])
            meshes[i]=(np.vstack([p for p,t in parts]),np.vstack([t+o for (p,t),o in zip(parts,offsets)]))
        ranked=sorted(meshes,key=lambda i:-len(meshes[i][1])); selected=set(ranked[:args.top])
        if asset=='tech-core':
            for key in ['core-head','core-arm']:
                selected.update(n['node'] for n in review['targets'][key]['collision']['nodes'][:args.top])
        # At most 20 additional >=80-triangle nodes per asset with promising cheap
        # roundness. Prioritize actual removable cost; all undergo full checks.
        extras=[]
        for i in ranked:
            if i in selected or len(meshes[i][1])<80: continue
            if cheap_roundness(meshes[i][0]) <= .0015: extras.append(i)
            if len(extras)==20: break
        selected.update(extras)
        coverage.append(dict(asset=asset,total_mesh_nodes=len(meshes),scanned_nodes=len(selected),additional_screened_round_nodes=extras,scanned_triangles=sum(len(meshes[i][1]) for i in selected),scene_triangles=meta['scene_triangles']))
        for i in sorted(selected,key=lambda i:-len(meshes[i][1])):
            if (asset,i) in old:
                row=old[(asset,i)]; assert row['source_sha256']==meta['sha256']; rows.append(row); continue
            p,t=meshes[i]; proposals=propose(p,t); fitted=[]
            for kind in ['cylinder','capsule','sphere']:
                choices=[]
                for sh in proposals:
                    if sh['kind']!=kind: continue
                    ev=evaluate(p,t,sh,False); choices.append((ev['score_mm'],sh))
                sh=min(choices,key=lambda a:a[0])[1]; ev=evaluate(p,t,sh)
                sh['axis_world']=np.asarray(sh['frame'])[:,2]
                sh['quaternion_xyzw']=Rotation.from_matrix(sh['frame']).as_quat()
                sh['center_node_local_m']=(np.linalg.inv(transforms[i])@np.r_[sh['center_m'],1])[:3]
                sh['axis_node_local']=np.linalg.solve(transforms[i][:3,:3],sh['axis_world'])
                fitted.append(dict(shape=sh,metrics=ev))
            best=min(fitted,key=lambda a:a['metrics']['score_mm']); score=best['metrics']['score_mm']; span=np.ptp(p,axis=0).max()
            status='low-deviation-review' if score<=1 and score/1000/span<=.015 else ('possible-review' if score<=3 and score/1000/span<=.04 else 'reject-single-rounded-shape')
            if asset=='tech-core' and i==22: status='existing-compound-reference-no-new-savings'
            if asset=='tech-core' and i in [17,1284]: status='existing-open-profile-reference-preserve-opening'
            row=dict(asset=asset,source=str(path.relative_to(ROOT)),source_sha256=meta['sha256'],node=i,node_name=doc['nodes'][i].get('name'),node_extras=doc['nodes'][i].get('extras',{}),component=components[i],ancestry=[dict(index=j,name=doc['nodes'][j].get('name'),extras=doc['nodes'][j].get('extras',{})) for j in ancestry[i]],node_world_matrix=transforms[i],coordinate_frame='source GLB active-scene world/rest pose, metres; NOT placed arena/FLU',placements=meta['placements'],source_triangles=len(t),placed_source_triangles=len(t)*meta['placements'],proposed_native_shapes=1,diagnostic_native_triangles=0,span_m=span,world_bounds_m=[p.min(axis=0),p.max(axis=0)],status=status,best_kind=best['shape']['kind'],fits=fitted,contact_approved=False)
            rows.append(row)
            print(asset,i,len(t),status,best['shape']['kind'],round(score,4),flush=True)
        assert sha(path)==meta['sha256']
    result=dict(schema='rounded-primitive-candidate-research-1',review_sha256=sha(refpath),method='Per rigid mesh node; enclosing cylinders from geometric axes; nonlinear capsule/sphere; exact analytic SDF and deterministic VTK surface distances. Finite samples, no contact approval.',coverage=coverage,candidates=rows)
    (OUT/'scan.json').write_text(json.dumps(result,indent=2,default=serial,allow_nan=False)+'\n')
    selected=[r for r in rows if r['status'] in ['low-deviation-review','possible-review']]
    (OUT/'shortlist.json').write_text(json.dumps(dict(**{k:v for k,v in result.items() if k!='candidates'},candidates=selected),indent=2,default=serial,allow_nan=False)+'\n')

if __name__=='__main__': main()
