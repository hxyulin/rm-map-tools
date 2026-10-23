"""Fit head vectors and export a distinct, explicitly non-runtime review recipe."""
import copy,json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from research import ROOT,OUT,p,scan
from gltf_scene import read_glb,write_glb,scene_nodes
from simplify_package import compact,scene_triangles

def hull_geometry(points):
    h=ConvexHull(points);t=h.simplices.copy();normal=np.cross(points[t[:,1]]-points[t[:,0]],points[t[:,2]]-points[t[:,0]])
    flip=np.einsum('ij,ij->i',normal,h.equations[:,:3])<0;t[flip]=t[flip][:,[0,2,1]]
    return points[t]

def compact_hull(points,tolerance=.25):
    ids=set()
    for direction in np.concatenate([np.eye(3),-np.eye(3)]):ids.add(int(np.argmax(points@direction)))
    # Thin plates can have coincident directional extrema; seed a full source hull.
    hull=ConvexHull(points)
    if len(ids)<4 or np.linalg.matrix_rank(points[list(ids)]-points[list(ids)].mean(0))<3:ids.update(hull.vertices[:8].tolist())
    for _ in range(200):
        selected=np.array(sorted(ids));geo=hull_geometry(points[selected])
        dist=p.distances(points,geo.reshape(-1,3),np.arange(len(geo)*3).reshape(-1,3));worst=int(dist.argmax())
        if dist[worst]<=tolerance:return points[selected],geo,float(dist.max())
        ids.add(worst)
    raise ValueError('hull vertex budget exhausted')

def box_geometry(shape):
    h=np.array(shape['half_extents_m'])*1000;center=np.array(shape['pose']['translation_m'])*1000
    frame=Rotation.from_quat(shape['pose']['rotation_xyzw']).as_matrix()
    pts=np.array([[x,y,z]for x in [-h[0],h[0]]for y in [-h[1],h[1]]for z in [-h[2],h[2]]])@frame.T+center
    return hull_geometry(pts)

def geometry(shape):
    if shape['kind']=='box':return box_geometry(shape)
    if shape['kind']=='convex_hull':
        frame=Rotation.from_quat(shape['pose']['rotation_xyzw']).as_matrix()
        pts=np.array(shape['vertices_local_m'])*1000@frame.T+np.array(shape['pose']['translation_m'])*1000
        return hull_geometry(pts)
    raise ValueError('head fit only exports boxes and hulls')

def samples(g):return p.probes(g,50000)

def main():
    screen_path=OUT/'screen.json';screen=json.loads(screen_path.read_text());source=Path(screen['source']);assert scan.digest(source)==screen['source_sha256']
    report_path=Path(screen['accepted_head_report']);r=json.loads(report_path.read_text());assert scan.digest(report_path)==screen['accepted_head_report_sha256']
    d,c,n=scan.load_nodes(source);parts=[];replacements={};measurements=[];rejected=[]
    frame=np.array(r['support_definition']['frame_columns']);shapes=[]
    for lo,hi in r['support_definition']['boxes_bounds_mm']:
        lo=np.array(lo);hi=np.array(hi)
        shapes.append(dict(kind='box',half_extents_m=((hi-lo)/2000).tolist(),pose=dict(translation_m=(((hi+lo)/2)@frame.T/1000).tolist(),rotation_xyzw=Rotation.from_matrix(frame).as_quat().tolist())))
    replacements[1668]=np.concatenate([geometry(s)for s in shapes]);parts.append((1668,shapes))
    fd=p.distances(samples(n[1668]),replacements[1668].reshape(-1,3),np.arange(84*3).reshape(-1,3))
    rd=p.distances(samples(replacements[1668]),n[1668].reshape(-1,3),np.arange(84*3).reshape(-1,3))
    assert max(fd.max(),rd.max())<.0003
    measurements.append(dict(node=1668,source_triangles=84,head_shapes=7,kind='box-compound',source_to_fit_max_mm=float(fd.max()),fit_to_source_max_mm=float(rd.max()),
        fit_is_exact_representation_within_float32_rounding=True))
    # Bounded screen found four long backing strips with <=1.6 mm coarse fits.
    # All larger perforated housings and the front interface stay original.
    for ni in [288,624,944,112]:
        row=next(x for x in screen['rows']if x['node']==ni);g=n[ni];points=np.unique(g.reshape(-1,3),axis=0)
        selected,geo,recession=compact_hull(points)
        forward=p.distances(samples(g),geo.reshape(-1,3),np.arange(len(geo)*3).reshape(-1,3))
        reverse=p.distances(samples(geo),g.reshape(-1,3),np.arange(len(g)*3).reshape(-1,3))
        if max(forward.max(),reverse.max())>2. or len(selected)>64:
            rejected.append(dict(node=ni,reason='refined max exceeds 2 mm or 64-vertex budget',forward_mm=float(forward.max()),reverse_mm=float(reverse.max()),vertices=len(selected)));continue
        center=selected.mean(0)
        shape=dict(kind='convex_hull',vertices_local_m=((selected-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1]))
        replacements[ni]=geometry(shape);parts.append((ni,[shape]))
        measurements.append(dict(node=ni,kind='compact-convex-hull',source_triangles=len(g),preview_triangles=len(geo),vertices=len(selected),source_vertex_recession_max_mm=recession,
            source_to_fit_max_mm=float(forward.max()),fit_to_source_max_mm=float(reverse.max()),samples_source=len(samples(g)),samples_fit=len(samples(geo)),
            caveat='Convex fitting closes fine source recesses/fastener gaps; finite surface samples and interface rays are required.'))
    target=OUT/'collision-tech-core.glb';check=p.replace(source,target,replacements)
    # Export a separate review schema so current cylinder-only runtime cannot
    # accidentally treat this mixed recipe as an installed collision contract.
    native_source=Path(r['head_source']);assert scan.digest(native_source)==r['head_source_sha256']
    native_before=json.loads((report_path.parent/'native/collision-shapes.json').read_text());native=copy.deepcopy(native_before['native_parts'])
    nd,nb=read_glb(native_source);parents={i:parent for i,w,parent in scene_nodes(nd)};worlds={i:w for i,w,parent in scene_nodes(nd)}
    for ni,ss in parts:
        assert np.array_equal(worlds[ni],np.eye(4));anc=[];j=ni
        while j is not None:anc.append(j);j=parents[j]
        for index,s in enumerate(ss):native.append(dict(id=f'node-{ni}-{index}',source_node_index=ni,source_node_name=nd['nodes'][ni]['name'],
            ancestor_nodes_root_first=anc[::-1],component_id=c[ni],review_status='head-vector-fit-not-runtime-approved',shape=s))
    selected_nodes=sorted(set(native_before['replaced_node_indices'])|set(replacements));remainder=copy.deepcopy(nd)
    removed=sum(sum(nd['accessors'][pr['indices']]['count']//3 for pr in nd['meshes'][nd['nodes'][i]['mesh']]['primitives'])for i in selected_nodes)
    for i in selected_nodes:del remainder['nodes'][i]['mesh']
    folder=OUT/'native-review';folder.mkdir(exist_ok=True);write_glb(folder/'remainder.glb',remainder,compact(remainder,nb))
    rem,_=read_glb(folder/'remainder.glb');native_exact=p.pair.unchanged(native_source,folder/'remainder.glb',set(selected_nodes))
    counts={kind:sum(x['shape']['kind']==kind for x in native)for kind in ['cylinder','box','convex_hull']}
    recipe=dict(schema='rm-map-tools.native-primitive-review-1',units='m',coordinate_frame='source_glb_active_scene',quaternion_order='xyzw',
        cylinder_local_axis='+Z',box_half_extents_axes='local XYZ',hull_vertices_frame='part pose local',source=dict(file=str(native_source),sha256=scan.digest(native_source)),
        retained_mesh=dict(file='remainder.glb',sha256=scan.digest(folder/'remainder.glb'),triangles=scene_triangles(rem)),replaced_node_indices=selected_nodes,
        removed_mesh_triangles=removed,native_parts=native,shape_counts=counts,runtime_supported=False,installed=False,
        required_runtime_work='Verified field sidecar currently accepts cylinders only. Box and convex-hull field loading must be added before using this review recipe. Engine native cooking already supports both.')
    (folder/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
    stage=json.loads((report_path.parent/'paired-stage.json').read_text());previous_field_native=r['field_native_mesh_triangles'];stage['collision_assets']['tech-core']=dict(path=str(target),sha256=scan.digest(target),triangles=check['after'],placements=2,placed_triangles=check['after']*2)
    total=sum(x['placed_triangles']for x in stage['collision_assets'].values());stage.update(variant='head-native-vector-fit-review',status='mixed native review recipe not runtime supported',placed_collision_triangles=total,installed=False,contact_validated=False)
    (OUT/'paired-stage.json').write_text(json.dumps(stage,indent=2)+'\n')
    head_removed=sum(len(n[i])for i in replacements);field_native=previous_field_native-2*head_removed
    pins={str(x):scan.digest(x)for x in [source,native_source,report_path,screen_path,Path(r['unchanged_visual']),report_path.parent/'native/collision-shapes.json']}
    for path,h in r['input_pins'].items():assert scan.digest(Path(path))==h;pins[path]=h
    result=dict(accepted_head_report=str(report_path),source_collision=str(source),source_collision_sha256=scan.digest(source),candidate_collision=str(target),candidate_sha256=scan.digest(target),
        unchanged_visual=r['unchanged_visual'],unchanged_visual_sha256=r['unchanged_visual_sha256'],changed_head_nodes=sorted(replacements),measurements=measurements,rejected_refinements=rejected,
        native_review=str(folder/'recipe.json'),native_shape_counts_per_core=counts,native_remaining_mesh_per_core=scene_triangles(rem),
        head_mesh_triangles_replaced_per_core=head_removed,additional_placed_native_mesh_triangles_removed=head_removed*2,
        preview_check=check,field_preview_triangles=total,field_native_mesh_triangles=field_native,field_native_shape_counts={k:v*2 for k,v in counts.items()},
        unchanged_native_remainder_owners_exact=native_exact,input_pins=pins,runtime_supported=False,installed=False,contact_validated=False)
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Fits',counts,'head triangles moved to vectors',head_removed*2,'field remaining mesh',field_native,flush=True)
    print('Refinements',measurements,'rejected',rejected,flush=True)

if __name__=='__main__':main()
