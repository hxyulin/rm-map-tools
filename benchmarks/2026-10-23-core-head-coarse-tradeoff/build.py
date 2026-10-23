"""Deliberate low-detail rigid head collision envelopes; visual bytes exact."""
import copy,importlib.util,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from shapely.geometry import Polygon,box as polygon_box
ROOT=Path(__file__).resolve().parents[2]
helper_path=str(ROOT/'benchmarks/2026-10-23-core-head-primitives');sys.path.insert(0,helper_path)
spec=importlib.util.spec_from_file_location('head_vector_helpers',ROOT/'benchmarks/2026-10-23-core-head-primitives/build.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
sys.path.remove(helper_path)
p=v.p;scan=v.scan
from gltf_scene import read_glb,write_glb,scene_nodes
from simplify_package import compact,scene_triangles
OUT=ROOT/'out/rmuc2027-core-head-coarse-tradeoff'
PREVIOUS=ROOT/'out/rmuc2027-core-head-primitives'

def aabb(lo,hi):
    lo=np.array(lo,float);hi=np.array(hi,float)
    return dict(kind='box',half_extents_m=((hi-lo)/2000).tolist(),pose=dict(translation_m=((hi+lo)/2000).tolist(),rotation_xyzw=[0,0,0,1]))

def subtract(bounds,cut):
    lo,hi=map(lambda x:np.array(x,float),bounds);cl,ch=map(lambda x:np.array(x,float),cut)
    il=np.maximum(lo,cl);ih=np.minimum(hi,ch)
    if (ih<=il).any():return [bounds]
    result=[];a=lo.copy();b=hi.copy()
    for axis in range(3):
        if a[axis]<il[axis]:
            end=b.copy();end[axis]=il[axis];result.append((a.copy(),end));a[axis]=il[axis]
        if b[axis]>ih[axis]:
            start=a.copy();start[axis]=ih[axis];result.append((start,b.copy()));b[axis]=ih[axis]
    return result

def prism(poly,front,back):
    xy=np.array(poly.exterior.coords)[:-1];points=np.concatenate([np.column_stack([xy,np.full(len(xy),z)])for z in [front,back]])
    h=ConvexHull(points);points=points[h.vertices];center=points.mean(0)
    return dict(kind='convex_hull',vertices_local_m=((points-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1]))

def envelopes(nodes,variant):
    # Source shell projection fixes the broad hexagonal outline. Internal shell
    # walls, panel recesses and vents deliberately become a solid collision skin.
    points=np.concatenate([nodes[i].reshape(-1,3)for i in [108,1266,1268,1254,1255]])
    xy=points[:,:2];hull=ConvexHull(xy);outline=Polygon(xy[hull.vertices]).simplify(3 if variant=='balanced'else 10,preserve_topology=True)
    shapes=[];labels=[]
    left,right=(-690.,-530.)if variant=='balanced'else(-680.,-545.)
    front=-548. if variant=='balanced'else-560.
    regions=[]
    if variant=='balanced':
        for lo,hi in [(-2000.,-963.),(-963.,0.)]:
            regions.extend([('left body',polygon_box(-1000,lo,left,hi),front),('right body',polygon_box(right,lo,0,hi),front)])
    else:regions=[('left body',polygon_box(-1000,-2000,left,0),front),('right body',polygon_box(right,-2000,0,0),front)]
    regions.extend([('lower end bridge',polygon_box(left,-2000,right,-1117 if variant=='balanced'else-1105),front),
        ('upper end bridge',polygon_box(left,-729 if variant=='balanced'else-720,right,0),-480.5 if variant=='balanced'else-508.)])
    for label,region,z in regions:
        poly=outline.intersection(region)
        if poly.is_empty or poly.area<1:continue
        assert poly.geom_type=='Polygon'
        shapes.append(prism(poly,z,-430.));labels.append(label)
    # Preserve two orthogonal approach channels, instead of filling the socket
    # just because the rear mechanism can use boxes.
    cuts=[([-625.,-2000.,-534.],[-600.,0.,-509.]),([-632.,-774.,-1000.],[-591.,-731.,0.])]
    mechanisms=[([-656.5,-871.7,-562.9],[-568.8,-798.7,-487.6]),([-640.8,-798.8,-562.8],[-584.4,-706.5,-488.])]
    box_bounds=[]
    for bounds in mechanisms:
        pieces=[bounds]
        for cut in cuts:pieces=[part for b in pieces for part in subtract(b,cut)]
        box_bounds.extend(pieces)
    for bounds in box_bounds:shapes.append(aabb(*bounds));labels.append('motor housing with approach clearance')
    # Three boxes retain the broad rear support and rail gap, dropping small
    # recesses/channels accepted in this deliberately coarse tradeoff.
    report=json.loads((ROOT/'out/rmuc2027-core-head-back-trial/compact-12mm/verification.json').read_text());frame=np.array(report['support_definition']['frame_columns'])
    rear=[([-665.5655,-991.5712,-469.2401],[-655.6654,-872.5711,-398.7401]),
        ([-579.4654,-991.5712,-469.2401],[-569.5653,-872.5711,-398.7401]),
        ([-655.6654,-983.5711,-426.7401],[-579.4654,-880.5711,-418.7401])]
    for lo,hi in rear:
        lo=np.array(lo);hi=np.array(hi);shapes.append(dict(kind='box',half_extents_m=((hi-lo)/2000).tolist(),
            pose=dict(translation_m=(((hi+lo)/2)@frame.T/1000).tolist(),rotation_xyzw=Rotation.from_matrix(frame).as_quat().tolist())));labels.append('coarse rear support')
    if variant=='lean':
        shapes.append(aabb([-690.6,-1116.9,-483.7],[-535.6,-683.2,-474.3]));labels.append('coarse central backing plate')
    return shapes,dict(outline_xy_mm=np.array(outline.exterior.coords).tolist(),body_inner_x_mm=[left,right],labels=labels,
        exact_clearance_cut_boxes_mm=cuts,mechanism_box_bounds_after_cuts_mm=[(np.array(lo).tolist(),np.array(hi).tolist())for lo,hi in box_bounds],
        deliberate_changes=['Rear/side recesses and internal assembly detail become solid collision volumes.','Motor and rear supports lose small cavities, ribs and fasteners.',
            'Balanced retains exact front mesh; lean replaces the slotted outer collision shell with a solid casing while visuals stay exact.',
            'Lean also approximates the central backing plate with a box.'])

def main(variants=('balanced','lean'),keep_override=None):
    OUT.mkdir(exist_ok=True);previous_path=PREVIOUS/'verification.json';old=json.loads(previous_path.read_text());source=Path(old['candidate_collision'])
    assert scan.digest(source)==old['candidate_sha256'];d,c,n=scan.load_nodes(source);head={i for i in n if c[i]=='technology-core/tool-head'}
    # All grouped owners live in the same currently rigid field component. Keep
    # the complete source node hierarchy so future per-part drivers can reject
    # this group rather than silently inherit a wrong rigid proxy.
    root=3;assert d['nodes'][root]['extras']['component_id']=='technology-core/tool-head'
    old_recipe=json.loads(Path(old['native_review']).read_text());native_source=Path(old_recipe['source']['file']);nd,nb=read_glb(native_source)
    field_base=old['field_native_mesh_triangles']-2*old['native_remaining_mesh_per_core'];rows=[]
    for variant in variants:
        out=OUT/variant;out.mkdir(exist_ok=True)
        keep={108,81,82,1284,1296,1297,1501}if variant=='balanced'else{1284,1296,1297,1501}
        if keep_override is not None:keep=set(keep_override)
        dropped=sorted(head-keep);assert 1668 in dropped
        shapes,definition=envelopes(n,variant);geo=np.concatenate([v.geometry(s)for s in shapes])
        intermediate=out/'proxy-source.glb';p.replace(source,intermediate,{1668:geo})
        td,tb=read_glb(intermediate)
        for i in dropped:
            if i!=1668:del td['nodes'][i]['mesh']
        target=out/'collision-tech-core.glb';write_glb(target,td,compact(td,tb))
        exact=p.pair.unchanged(source,target,set(dropped));actual,_=read_glb(target);preview_count=scene_triangles(actual)
        head_mesh=sum(len(n[i])for i in keep);source_group_mesh=sum(len(n[i])for i in dropped)
        # New component-level review group supersedes all prior head primitives.
        # This is deliberately not a runtime-v1 per-owner cylinder contract.
        native=[copy.deepcopy(x)for x in old_recipe['native_parts']if x['component_id']!='technology-core/tool-head']
        assert len(native)==39
        for index,shape in enumerate(shapes):native.append(dict(id=f'head-envelope-{index}',source_node_index=root,source_node_name=d['nodes'][root]['name'],
            ancestor_nodes_root_first=[0,3],component_id='technology-core/tool-head',source_group='rigid-head-envelope',shape=shape))
        old_arm_nodes={x['source_node_index']for x in native if x.get('source_group')!='rigid-head-envelope'}
        remainder=copy.deepcopy(nd);remove=set(dropped)|old_arm_nodes
        for i in remove:del remainder['nodes'][i]['mesh']
        folder=out/'native-review';folder.mkdir(exist_ok=True);write_glb(folder/'remainder.glb',remainder,compact(remainder,nb));rem,_=read_glb(folder/'remainder.glb')
        native_exact=p.pair.unchanged(native_source,folder/'remainder.glb',remove)
        counts={kind:sum(x['shape']['kind']==kind for x in native)for kind in ['cylinder','box','convex_hull']}
        group=dict(id='rigid-head-envelope',component_root_node=root,covered_source_mesh_nodes=dropped,
            rigid_owner_requirement='All covered leaves must remain bound to this one rigid field head component; reject future per-leaf motion drivers.',
            current_equipment_manifest='No Tech Core semantics/motion binding declared in installed equipment manifest.',definition=definition)
        recipe=dict(schema='rm-map-tools.native-component-envelope-review-1',units='m',coordinate_frame='source_glb_active_scene',quaternion_order='xyzw',cylinder_local_axis='+Z',
            source=dict(file=str(native_source),sha256=scan.digest(native_source)),retained_mesh=dict(file='remainder.glb',sha256=scan.digest(folder/'remainder.glb'),triangles=scene_triangles(rem)),
            replaced_node_indices=sorted(remove),source_groups=[group],native_parts=native,shape_counts=counts,runtime_supported=False,installed=False)
        (folder/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
        stage=json.loads((PREVIOUS/'paired-stage.json').read_text());stage['collision_assets']['tech-core']=dict(path=str(target),sha256=scan.digest(target),triangles=preview_count,placements=2,placed_triangles=preview_count*2)
        field_preview=sum(x['placed_triangles']for x in stage['collision_assets'].values());stage.update(variant=f'head-coarse-{variant}',status='coarse contact/performance tradeoff review; not runtime supported',placed_collision_triangles=field_preview,installed=False,contact_validated=False)
        (out/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
        pins={str(path):scan.digest(path)for path in [source,previous_path,Path(old['native_review']),native_source,Path(old['unchanged_visual']),PREVIOUS/'paired-stage.json']}
        for path,h in old['input_pins'].items():assert scan.digest(Path(path))==h;pins[path]=h
        report=dict(variant=variant,source_collision=str(source),source_collision_sha256=scan.digest(source),candidate_collision=str(target),candidate_sha256=scan.digest(target),
            unchanged_visual=old['unchanged_visual'],unchanged_visual_sha256=old['unchanged_visual_sha256'],kept_head_nodes=sorted(keep),grouped_head_nodes=dropped,
            proxy_preview_owner=1668,definition=definition,head_mesh_triangles_kept=head_mesh,head_native_shapes=len(shapes),proxy_preview_triangles=len(geo),
            source_head_triangles=sum(len(n[i])for i in head),head_preview_triangles=head_mesh+len(geo),collision_preview_triangles_per_core=preview_count,
            native_remaining_mesh_per_core=scene_triangles(rem),native_shape_counts_per_core=counts,source_group_mesh_triangles_replaced=source_group_mesh,
            source_group_owner_count=len(dropped),field_preview_triangles=field_preview,field_native_mesh_triangles=field_base+2*scene_triangles(rem),
            field_native_shape_counts={k:2*val for k,val in counts.items()},unchanged_other_preview_owners_exact=exact,unchanged_native_remainder_owners_exact=native_exact,
            native_review=str(folder/'recipe.json'),input_pins=pins,runtime_supported=False,installed=False,contact_validated=False)
        (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');rows.append(dict(variant=variant,path=str(out/'verification.json'),sha256=scan.digest(out/'verification.json')))
        print(variant,'head mesh',head_mesh,'+',len(shapes),'shapes; preview',head_mesh+len(geo),'field mesh',report['field_native_mesh_triangles'],counts,flush=True)
    (OUT/'variants.json').write_text(json.dumps(rows,indent=2)+'\n')

if __name__=='__main__':main()
