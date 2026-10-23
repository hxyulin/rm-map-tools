"""Enrich scanner evidence, score explicit cavity/detail filling, render matched pairs.

Does not alter GLBs. Uses an existing raster executable (no build).
"""
import json, sys, copy
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation
from scan import ROOT, OUT, sha, serial, evaluate, diagnostic_mesh
from gltf_scene import read_glb, mesh_instances
from mesh_quality import distances
import collision_review_render as renderer

def geometry(path,node):
    doc,blob=read_glb(path); parts=[(p,t) for i,_,p,t,_ in mesh_instances(doc,blob) if i==node]
    offsets=np.cumsum([0]+[len(p) for p,t in parts[:-1]])
    return np.vstack([p for p,t in parts]),np.vstack([t+o for (p,t),o in zip(parts,offsets)])

def axis_intersections(p,t,shape):
    # Two-sided Moller-Trumbore infinite-axis intersections; deduplicate shared edges.
    a=np.asarray(shape['axis_world']); c=np.asarray(shape['center_m']); q=p[t]
    e1=q[:,1]-q[:,0];e2=q[:,2]-q[:,0];h=np.cross(np.broadcast_to(a,e2.shape),e2);det=np.einsum('ij,ij->i',e1,h)
    good=abs(det)>1e-14; inv=np.zeros_like(det);inv[good]=1/det[good]
    s=c-q[:,0];u=np.einsum('ij,ij->i',s,h)*inv;v=np.cross(s,e1)@a*inv;z=np.einsum('ij,ij->i',e2,np.cross(s,e1))*inv
    z=np.sort(z[good&(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8)])
    if len(z):z=z[np.r_[True,np.diff(z)>1e-7]]
    return z.tolist()

def data(p,t,color):
    g=p[t];return(g,np.tile(color,(len(t),1)),np.zeros((len(t),3,2)),np.zeros(len(t),dtype=np.int32),None,np.full((1,1,3),255,dtype=np.uint8))

def main():
    src=OUT/'scan.json'; scan=json.loads(src.read_text()); review=json.loads((ROOT/'out/rmuc2027-installed-reference-review/review.json').read_text())
    placements={}; pins={}
    for p,h in review['pins'].items():
        path=Path(p)
        if path.name=='manifest.json':
            assert sha(path)==h;pins[p]=h
            placements.update({k:v['placements_in_source_arena_frame'] or [{}] for k,v in json.loads(path.read_text())['assets'].items()})
    selected=[]; representative=[]
    for r in scan['candidates']:
        fits=r['fits']; best=min(fits,key=lambda f:f['metrics']['score_mm']); m=best['metrics']; span=r['span_m']
        strict=max(m['forward_absolute_surface']['max_mm'],m['reverse_surface']['max_mm'])
        r['strict_bidirectional_max_mm']=strict
        r['strict_bidirectional_max_fraction_span']=strict/1000/span
        r['external_solid_score_mm']=m['score_mm']
        original=r['status']; conditional=False
        if original not in ['existing-compound-reference-no-new-savings','existing-open-profile-reference-preserve-opening']:
            if strict<=1 and strict/1000/span<=.015: r['status']='strong-sampled-surface-candidate'
            elif strict<=3 and strict/1000/span<=.04:r['status']='moderate-sampled-surface-candidate'
            elif original in ['low-deviation-review','possible-review']:
                r['status']='conditional-filled-cavity-or-detail-candidate';conditional=True
            else:r['status']='reject-single-rounded-shape'
        r['native_replacement_triangle_count']=0
        r['new_savings_eligible']=r['status'] in ['strong-sampled-surface-candidate','moderate-sampled-surface-candidate','conditional-filled-cavity-or-detail-candidate']
        r['provisional_placed_triangles_removed']=r['placed_source_triangles'] if r['new_savings_eligible'] else 0
        # Preserve exact owner ancestry; all world positions are rest pose only.
        for fit in fits:
            sh=fit['shape'];sh['placed_source_arena_poses']=[]
            for index,ps in enumerate(placements[r['asset']]):
                rot=Rotation.from_quat(ps.get('rotation_xyzw',[0,0,0,1]));tr=np.asarray(ps.get('translation_m',[0,0,0]))
                sh['placed_source_arena_poses'].append(dict(placement=index,center_m=rot.apply(sh['center_m'])+tr,axis=rot.apply(sh['axis_world']),quaternion_xyzw=(rot*Rotation.from_quat(sh['quaternion_xyzw'])).as_quat()))
        if r['new_savings_eligible'] or (r['asset']=='tech-core' and r['node'] in [17,18,22,47,108,1284,1120,1664]):
            p,t=geometry(ROOT/r['source'],r['node']); cylinder=next(f for f in fits if f['shape']['kind']=='cylinder');sh=cylinder['shape'];a=np.asarray(sh['axis_world']);c=np.asarray(sh['center_m']);h=sh['length_m']/2
            centers=np.vstack([c-h*a,c+h*a]); cd=distances(centers,p,t)
            r['filled_cavity_diagnostic']=dict(policy='Scored intentional solid filling only as an investigation; openings/recesses NOT approved to close.',source_inside_depth_max_mm=cylinder['metrics']['source_inside_depth_max_mm'],source_inside_samples_over_1mm=cylinder['metrics']['source_inside_solid_over_1mm'],flat_cap_center_to_source_mm=cd*1000,axis_source_intersections_offsets_m=axis_intersections(p,t,sh),interpretation='Deep source-inside samples measure filled recesses/cavities or over-envelope, not outside omission. Cap center and axis rays diagnose central openings only; offset bores remain unresolved.',volume_of_solid_cylinder_mm3=np.pi*sh['radius_m']**2*sh['length_m']*1e9)
            # Conventional same-axis alternatives avoid relying solely on unstable
            # nonlinear surface fits (e.g. a sphere fitting a flat plate at infinity).
            alternatives=[]
            for mode in ['same-total-extent-capsule','same-barrel-capsule','enclosing-sphere']:
                s=copy.deepcopy(sh)
                if mode=='enclosing-sphere':s['kind']='sphere';s['radius_m']=float(np.linalg.norm(p-c,axis=1).max())
                else:s['kind']='capsule';s['segment_length_m']=max(sh['length_m']-2*sh['radius_m'],0) if mode=='same-total-extent-capsule' else sh['length_m']
                alternatives.append(dict(mode=mode,shape=s,metrics=evaluate(p,t,s)))
            r['conventional_alternatives']=alternatives
            representative.append(r)
            if r['new_savings_eligible']: selected.append(r)
    summary=dict(schema='rounded-primitive-shortlist-research-2',source_review_sha256=scan['review_sha256'],scan_sha256=sha(src),manifest_pins=pins,coverage=scan['coverage'],scope='Collision only. Per rigid node and original ancestry; rest poses do not establish articulated clearance/contact. Native shapes have zero surface triangles; GLB diagnostic meshes are not native runtime shapes.',limits='Finite deterministic vertices/all triangle centroids/all edge midpoints; exact analytic SDF; reverse analytic surface lattice to original triangles using mesh_quality.distances VTK. Not a continuous Hausdorff/contact proof. No shape type exhaustively optimized. Axis rays miss offset cavities. No speedup claim.',candidates=selected,priority_core_and_rejection_evidence=[r for r in representative if not r['new_savings_eligible']],provisional_totals=dict(nodes=len(selected),native_shapes_per_asset_instances=sum(r['placements'] for r in selected),placed_source_triangles=sum(r['placed_source_triangles'] for r in selected),existing_core_node22_counted=False))
    (OUT/'shortlist.json').write_text(json.dumps(summary,indent=2,default=serial,allow_nan=False)+'\n')
    # Full classified evidence, including all rejects.
    (OUT/'classified-scan.json').write_text(json.dumps(scan,indent=2,default=serial,allow_nan=False)+'\n')
    helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
    if not helper.exists():print('No existing raster helper; skip renders');return
    work=OUT/'raster-work';work.mkdir(exist_ok=True)
    views=[]; thumbs=[]
    render_rows=selected+[r for r in representative if r['asset']=='tech-core' and r['node'] in [17,18,47,108,1284]]
    for r in render_rows:
        p,t=geometry(ROOT/r['source'],r['node']);sh=next(f['shape'] for f in r['fits'] if f['shape']['kind']==r['best_kind']);ap,at=diagnostic_mesh(sh)
        before=data(p,t,[.5,.65,.82]);after=data(ap,at,[.94,.61,.24]);focus=np.concatenate([before[0],after[0]])
        for view,direction in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
            pair=[]
            for stage,d in [('before',before),('diagnostic-after',after)]:
                im=Image.fromarray(renderer.raster(d,focus,direction,helper,work));path=OUT/f"{r['asset']}-node-{r['node']}-{view}-{stage}.webp";im.save(path,lossless=True)
                views.append(dict(asset=r['asset'],node=r['node'],stage=stage,view=view,path=str(path.relative_to(ROOT)),sha256=sha(path),direction=direction,frame='source GLB world, no placement; matched union bounds',focus_bounds_m=[focus.min((0,1)),focus.max((0,1))]))
                pair.append(im.resize((380,380)))
            if view=='oblique':
                tile=Image.new('RGB',(780,420),'white');draw=ImageDraw.Draw(tile);draw.text((8,5),f"{r['asset']} node {r['node']} | before / diagnostic {r['best_kind']}",fill='black');tile.paste(pair[0],(0,32));tile.paste(pair[1],(395,32));thumbs.append(tile)
    if thumbs:
        sheet=Image.new('RGB',(1560,420*((len(thumbs)+1)//2)),(230,230,230))
        for i,im in enumerate(thumbs):sheet.paste(im,((i%2)*780,(i//2)*420))
        sheet.save(OUT/'matched-contact-sheet.jpg',quality=90)
    (OUT/'renders.json').write_text(json.dumps(views,indent=2,default=serial)+'\n')
    for asset,meta in review['roles']['collision']['assets'].items():assert sha(ROOT/'out/rmuc2027-installed-reference-review/reference/collision'/f'{asset}.glb')==meta['sha256']
    print(json.dumps(summary['provisional_totals']))
    for r in selected:print(r['asset'],r['node'],r['status'],r['source_triangles'],r['strict_bidirectional_max_mm'],r['external_solid_score_mm'])

if __name__=='__main__':main()
