"""Purpose-built Rune hub envelopes with axial/radial arm separation."""
import copy,json,sys
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from shapely.geometry import Polygon,box
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-rune-hub-solid-trial'))
import hub
p=hub.p;v=hub.v;scan=hub.scan
from gltf_scene import read_glb,write_glb,scene_nodes
from simplify_package import compact,scene_triangles
OUT=ROOT/'out/rmuc2027-rune-hub-coarse'
BASE=hub.OUT/'open-centers/verification.json'
STAGE=hub.OUT/'open-centers/paired-stage.json'
BINDINGS=hub.BINDINGS
old_geometry=v.geometry

def geometry(s):
 if s['kind']!='cylinder':return old_geometry(s)
 frame=Rotation.from_quat(s['pose']['rotation_xyzw']).as_matrix()
 return p.cylinder(dict(center_m=s['pose']['translation_m'],axis_unit_vector=frame[:,2].tolist(),radius_m=s['radius_m'],length_m=s['length_m']))
v.geometry=geometry

def shape_box(lo,hi,frame,pivot):
 lo=np.array(lo,float);hi=np.array(hi,float)
 return dict(kind='box',half_extents_m=((hi-lo)/2000).tolist(),pose=dict(translation_m=(((lo+hi)/2)@frame.T/1000+pivot/1000).tolist(),rotation_xyzw=Rotation.from_matrix(frame).as_quat().tolist()))

def prism(poly,z0,z1,frame,pivot):
 xy=np.array(poly.exterior.coords)[:-1];points=np.concatenate([np.column_stack([xy,np.full(len(xy),z)])for z in [z0,z1]])@frame.T+pivot;center=points.mean(0)
 return dict(kind='convex_hull',vertices_local_m=((points-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1]))

def annulus(radius,z0,z1,frame,pivot):
 theta=np.arange(8)*np.pi/4;poly=Polygon(np.column_stack([np.cos(theta),np.sin(theta)])*radius);a=58.;R=radius+1
 regions=[box(-R,a,R,R),box(-R,-R,R,-a),box(-R,-a,-a,a),box(a,-a,R,a)]
 return[prism(poly.intersection(region),z0,z1,frame,pivot)for region in regions]

def main():
 OUT.mkdir(exist_ok=True);base=json.loads(BASE.read_text());stage=json.loads(STAGE.read_text());source=Path(base['source_collision']);d,c,n=scan.load_nodes(source);bindings=json.loads(BINDINGS.read_text());parents={i:parent for i,w,parent in scene_nodes(d)}
 for variant in ['simple-frame','coarse-hub']:
  out=OUT/variant;out.mkdir(exist_ok=True);parts=[];replacements={};omitted=set();definitions=[];bank_nodes={}
  for bankidx,motion in enumerate(bindings['rune_motion']):
   bank='bank-a'if bankidx==0 else'bank-b';disk=272 if bankidx==0 else 426;ring=273 if bankidx==0 else 427;owner=274 if bankidx==0 else 428
   axis=np.array(motion['axis']);a,u,w=p.basis(axis);frame=np.column_stack([u,w,a]);pivot=np.array(motion['pivot_m'])*1000
   diskpts=(n[disk].reshape(-1,3)-pivot)@frame;xy=(diskpts[:,:2].min(0)+diskpts[:,:2].max(0))/2;radius=np.linalg.norm(diskpts[:,:2]-xy,axis=1).max();z0,z1=diskpts[:,2].min(),diskpts[:,2].max();center=np.r_[xy,(z0+z1)/2]
   cylinder=dict(kind='cylinder',radius_m=float(radius/1000),length_m=float((z1-z0)/1000),pose=dict(translation_m=(center@frame.T/1000+pivot/1000).tolist(),rotation_xyzw=Rotation.from_matrix(frame).as_quat().tolist()))
   selected={disk:[cylinder]};definition=dict(bank=bank,frame_columns=frame.tolist(),pivot_mm=pivot.tolist(),disk_radius_mm=float(radius),disk_length_mm=float(z1-z0),central_square_half_width_mm=58.)
   if variant=='simple-frame':
    q=(n[ring].reshape(-1,3)-pivot)@frame;lo,hi=q.min(0),q.max(0);lo[:2]=[-125,-125];hi[:2]=[125,125]
    bounds=[([lo[0],58,lo[2]],[hi[0],hi[1],hi[2]]),([lo[0],lo[1],lo[2]],[hi[0],-58,hi[2]]),([lo[0],-58,lo[2]],[-58,58,hi[2]]),([58,-58,lo[2]],[hi[0],58,hi[2]])]
    selected[ring]=[shape_box(a,b,frame,pivot)for a,b in bounds];definition['square_frame_outer_width_mm']=250.;definition['square_frame_axial_mm']=[float(lo[2]),float(hi[2])]
   else:
    # Big rear ring stops 5 mm before every arm axial sample. A narrow neck
    # remains at least 14 mm radially inside every arm source vertex.
    ids={i for i in n if c[i]==f'rune/banks/{bank}/hub-cluster'};bank_nodes[bank]=sorted(ids)
    arms=np.concatenate([g.reshape(-1,3)for i,g in n.items()if c[i].startswith(f'rune/banks/{bank}/arm-')]);q=(arms-pivot)@frame;arm_axial=[float(q[:,2].min()),float(q[:,2].max())];arm_radial=float(np.linalg.norm(q[:,:2],axis=1).min())
    if bankidx==0:rear=[-176.,arm_axial[0]-5];neck=[rear[1],45.5]
    else:rear=[arm_axial[1]+5,176.];neck=[-45.5,rear[0]]
    selected[owner]=annulus(311.,*rear,frame,pivot)+annulus(140.,*neck,frame,pivot)
    # One distinct reverse-side bracket has no matching bank-A part; retain it.
    keep_extra={429}if bankidx==1 else set();omitted|=ids-set(selected)-keep_extra
    definition.update(rear_ring_radius_mm=311.,rear_ring_axial_mm=rear,neck_radius_mm=140.,neck_axial_mm=neck,source_arm_axial_mm=arm_axial,source_arm_radial_min_mm=arm_radial,retained_extra_nodes=sorted(keep_extra),omitted_hardware_nodes=sorted(ids-set(selected)-keep_extra))
   for i,shapes in selected.items():
    replacements[i]=np.concatenate([geometry(s)for s in shapes]);anc=[];j=i
    while j is not None:anc.append(j);j=parents[j]
    for index,s in enumerate(shapes):parts.append(dict(id=f'{variant}-{i}-{index}',source_node_index=i,source_node_name=d['nodes'][i]['name'],ancestor_nodes_root_first=anc[::-1],component_id=c[i],shape=s))
   definitions.append(definition)
  selected=set(replacements)|omitted;temporary=out/'replaced.glb';hub.replace(source,temporary,replacements);td,tb=read_glb(temporary)
  for i in omitted:del td['nodes'][i]['mesh']
  target=out/'rune-collision.glb';write_glb(target,td,compact(td,tb));exact=p.pair.unchanged(source,target,selected);td,_=read_glb(target)
  remainder=copy.deepcopy(d);_,blob=read_glb(source)
  for i in selected:del remainder['nodes'][i]['mesh']
  folder=out/'native-review';folder.mkdir(exist_ok=True);write_glb(folder/'remainder.glb',remainder,compact(remainder,blob));rd,_=read_glb(folder/'remainder.glb');p.pair.unchanged(source,folder/'remainder.glb',selected)
  recipe=dict(schema='rm-map-tools.native-primitive-review-1',units='m',coordinate_frame='source_glb_active_scene',quaternion_order='xyzw',cylinder_local_axis='+Z',source=dict(file=str(source),sha256=scan.digest(source)),retained_mesh=dict(file='remainder.glb',sha256=scan.digest(folder/'remainder.glb'),triangles=scene_triangles(rd)),replaced_node_indices=sorted(selected),native_parts=parts,deliberately_omitted_nodes=sorted(omitted),runtime_supported=False,installed=False)
  (folder/'recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
  ns=copy.deepcopy(stage);count=scene_triangles(td);ns['collision_assets']['rune']=dict(path=str(target),sha256=scan.digest(target),triangles=count,placements=1,placed_triangles=count);ns['placed_collision_triangles']=sum(x['placed_triangles']for x in ns['collision_assets'].values());ns.update(variant='rune-hub-'+variant,installed=False,contact_validated=False);(out/'paired-stage.json').write_text(json.dumps(ns,indent=2)+'\n')
  removed=sum(len(n[i])for i in selected);base_before=json.loads(hub.BASE.read_text());counts={kind:sum(s['shape']['kind']==kind for s in parts)for kind in ['cylinder','box','convex_hull']}
  report=dict(variant=variant,source_collision=str(source),source_sha256=scan.digest(source),candidate_collision=str(target),candidate_sha256=scan.digest(target),selected_nodes=sorted(selected),omitted_nodes=sorted(omitted),definitions=definitions,native_review=str(folder/'recipe.json'),native_shape_counts=counts,native_shapes=len(parts),source_mesh_triangles_replaced=removed,native_rune_remaining_mesh_triangles=scene_triangles(rd),diagnostic_rune_triangles=count,
   field_native_mesh_triangles=base_before['field_native_mesh_triangles']-removed,field_native_shape_counts={kind:base_before['field_native_shape_counts'][kind]+counts[kind]for kind in counts},field_preview_triangles=ns['placed_collision_triangles'],unchanged_owners_exact=exact,unchanged_visual=base['unchanged_visual'],unchanged_visual_sha256=base['unchanged_visual_sha256'],input_pins={str(path):scan.digest(path)for path in [BASE,STAGE,BINDINGS,source,Path(base['unchanged_visual'])]},runtime_supported=False,installed=False,contact_validated=False)
  (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(variant,'removed',removed,'mesh; remaining',scene_triangles(rd),'+',counts,flush=True)
if __name__=='__main__':main()
