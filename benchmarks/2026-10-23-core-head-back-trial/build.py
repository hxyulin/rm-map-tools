"""Collision-only rear support and compact detail omission, preserving tool face.

All visual bytes stay exact. The front interface rectangle is a keep scope, not
a distance-based exception. Deleted collision owners keep empty named nodes.
"""
import copy,json,sys
from pathlib import Path
import numpy as np
from survey import ROOT,OUT,p
from scipy.spatial import ConvexHull
from gltf_scene import read_glb,write_glb
from simplify_package import compact,scene_triangles

def box(lo,hi,frame):
    lo=np.array(lo);hi=np.array(hi)
    pts=np.array([[x,y,z]for x in [lo[0],hi[0]]for y in [lo[1],hi[1]]for z in [lo[2],hi[2]]])@frame.T
    hull=ConvexHull(pts);tri=hull.simplices.copy();normal=np.cross(pts[tri[:,1]]-pts[tri[:,0]],pts[tri[:,2]]-pts[tri[:,0]])
    flip=np.einsum('ij,ij->i',normal,hull.equations[:,:3])<0;tri[flip]=tri[flip][:,[0,2,1]]
    return pts[tri]

def support():
    x=np.array([.99995625,0,.009354]);x/=np.linalg.norm(x);frame=np.column_stack([x,[0,1,0],np.cross(x,[0,1,0])])
    # Source dominant face planes, in the yaw-corrected local box frame.
    # Keep 76.2 mm between rails and the central 50 x 30 mm recess.
    # The middle U-shaped rib has two narrow walls and a recessed bottom.
    boxes=[([-665.5655,-991.5712,-469.2401],[-655.6654,-872.5711,-398.7401]),
        ([-579.4654,-991.5712,-469.2401],[-569.5653,-872.5711,-398.7401]),
        ([-655.6654,-931.0711,-426.7401],[-579.4654,-880.5711,-418.7401]),
        ([-655.6654,-983.5711,-426.7401],[-579.4654,-936.0711,-418.7401]),
        ([-650.6654,-936.0712,-469.2401],[-642.5654,-931.0711,-426.7401]),
        ([-592.5654,-936.0712,-469.2401],[-584.4654,-931.0711,-426.7401]),
        ([-642.5654,-936.0712,-439.2401],[-592.5654,-931.0711,-426.7401])]
    return np.concatenate([box(lo,hi,frame)for lo,hi in boxes]),dict(frame_columns=frame.tolist(),boxes_bounds_mm=boxes,
        rail_gap_mm=76.2,central_recess_width_mm=50.,central_recess_depth_mm=30.,status='manual_collision_support_seven_boxes',native_box_imported=False)

def omissions(d,components,nodes,limit):
    neutral={i for i,m in enumerate(d['materials'])if max(m.get('extras',{}).get('step_colour_srgb',[1,0,1]))-min(m.get('extras',{}).get('step_colour_srgb',[1,0,1]))<.02 and max(m.get('extras',{}).get('step_colour_srgb',[1,0,1]))<.6}
    remove=[];guarded=[]
    for i,g in nodes.items():
        if components[i]!='technology-core/tool-head':continue
        lo=g.min((0,1));hi=g.max((0,1))
        if max(hi-lo)>limit:continue
        materials={pr['material']for pr in d['meshes'][d['nodes'][i]['mesh']]['primitives']}
        if not materials<=neutral:continue
        if hi[0]>=-690 and lo[0]<=-530 and hi[1]>=-900 and lo[1]<=-670:guarded.append(i);continue
        remove.append(i)
    return remove,guarded

def omit(source,target,ids):
    d,b=read_glb(source);a=copy.deepcopy(d)
    for i in ids:del a['nodes'][i]['mesh']
    write_glb(target,a,compact(a,b))
    return p.pair.unchanged(source,target,set(ids))

def main():
    survey=json.loads((OUT/'survey.json').read_text());installed=Path(survey['source']);assert p.scan.digest(installed)==survey['source_sha256']
    rule_path=ROOT/'rules/collision-core-arm-reviewed-rmuc2027.json';rule=json.loads(rule_path.read_text())
    approved=ROOT/'out/rmuc2027-core-arm-checkpoint/collision-tech-core.glb';visual=ROOT/'out/rmuc2027-core-arm-checkpoint/visual-tech-core.glb'
    assert p.scan.digest(approved)==rule['canonical_outputs']['files']['collision-tech-core.glb']
    assert p.scan.digest(visual)==rule['canonical_outputs']['files']['visual-tech-core.glb']
    d,c,n=p.scan.load_nodes(installed);head={i for i in n if c[i]=='technology-core/tool-head'};proxy,definition=support()
    original=n[1668];support_errors=dict(source_to_proxy=p.surface(original,proxy),proxy_to_source=p.surface(proxy,original))
    results=[]
    for limit in [8,12]:
        out=OUT/f'compact-{limit}mm';out.mkdir(exist_ok=True)
        ids,guarded=omissions(d,c,n,limit);assert 1668 not in ids
        head_source=out/'head-source.glb';intermediate=out/'head-support-source.glb'
        p.replace(installed,intermediate,{1668:proxy});omit(intermediate,head_source,ids)
        # Compose onto approved canonical arm; all arm/mount arrays remain exact.
        composed=out/'support-with-approved-arm.glb';p.replace(approved,composed,{1668:proxy})
        target=out/'collision-tech-core.glb';exact=omit(composed,target,ids)
        actual,_=read_glb(target);new_count=scene_triangles(actual);saving=rule['counts_per_core']['collision_preview']-new_count
        selection=copy.deepcopy(rule['native_selection']);selection['source_sha256']=p.scan.digest(head_source)
        native=p.export_native(head_source,selection,out/'native')
        stage_path=ROOT/'out/rmuc2027-core-joints-base-r3/paired-stage.json';stage=json.loads(stage_path.read_text())
        stage['collision_assets']['tech-core']=dict(path=str(target),sha256=p.scan.digest(target),triangles=new_count,placements=2,placed_triangles=new_count*2)
        field_preview=sum(x['placed_triangles']for x in stage['collision_assets'].values())
        stage.update(variant=f'head-collision-compact-{limit}mm',status='unreviewed collision-only head trial over approved arm/base',placed_collision_triangles=field_preview,installed=False,contact_validated=False)
        (out/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
        removals=[dict(node=i,name=d['nodes'][i]['name'],triangles=len(n[i]),bounds_mm=[n[i].min((0,1)).tolist(),n[i].max((0,1)).tolist()])for i in ids]
        pins={str(x):p.scan.digest(x)for x in [installed,approved,visual,rule_path,OUT/'survey.json',stage_path]}
        for path,h in json.loads((ROOT/'rules/manual-review-reference-rmuc2027.json').read_text())['pins'].items():assert p.scan.digest(Path(path))==h;pins[path]=h
        report=dict(variant=f'compact-{limit}mm',source_collision=str(installed),approved_collision=str(approved),candidate_collision=str(target),candidate_sha256=p.scan.digest(target),
            unchanged_visual=str(visual),unchanged_visual_sha256=p.scan.digest(visual),head_source=str(head_source),head_source_sha256=p.scan.digest(head_source),
            support_node=1668,support_definition=definition,support_source_triangles=len(original),support_proxy_triangles=len(proxy),support_errors=support_errors,
            omitted_collision_owners=removals,omitted_triangles_per_core=sum(len(n[i])for i in ids),guarded_compact_owners=guarded,
            interface_keep_rectangle_source_mm=dict(x=[-690,-530],y=[-900,-670],z='all'),
            source_head_triangles=37574,candidate_head_triangles=37574-saving,collision_preview_triangles_per_core=new_count,placed_mesh_saving=saving*2,
            field_preview_triangles=field_preview,field_native_mesh_triangles=field_preview-39*96*2,field_visual_triangles=stage['placed_visual_triangles'],
            native_remaining_mesh_per_core=native['retained_mesh']['triangles'],native_cylinders_per_core=len(native['native_parts']),unchanged_other_collision_mesh_owners_exact=exact,
            names_transforms_ancestry_materials_exact=True,input_pins=pins,installed=False,contact_validated=False,
            caveats=['Compact neutral geometry is omitted as collision detail; source product naming does not establish that every leaf is a screw.',
                'Front interface rectangle keeps every overlapping compact owner. All colored/white optics and full visual payloads stay exact.',
                'Rear support uses seven mesh boxes, not imported native boxes. Rail spacing and central recess remain, while small holes/channels close.',
                'Empty omitted-owner nodes remain named with original ancestry; meshes alone are absent.',
                'Native bundle source is the explicitly modified head-source GLB plus original approved arm cylinder selectors. Original installed hash is retained as provenance.',
                'No all-pose contact, projectile route, runtime physics or speed approval.'])
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');results.append(dict(variant=report['variant'],path=str(out/'verification.json'),sha256=p.scan.digest(out/'verification.json')))
        print(report['variant'],'removed owners',len(ids),'triangles saved',saving*2,'head/Core',report['candidate_head_triangles'],'support errors',support_errors,flush=True)
    (OUT/'variants.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
