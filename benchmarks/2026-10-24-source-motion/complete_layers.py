"""Manual review partitions; preserve every source triangle, without cutting faces."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from export_field_package import GlbWriter
from gltf_scene import read_glb,mesh_instances
OUT=ROOT/'out/rmuc2027-source-motion';PIPE=ROOT/'out/rmuc2027-equipment-pipeline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
src=PIPE/'outpost/fixed/upper-cluster/native.npz';assert sha(src)==json.loads((src.parent/'native.json').read_text())['native_npz_sha256'];z=np.load(src);p=z['positions_mm'];tri=z['triangles'];q=p[tri];rad=np.linalg.norm(q[:,:,[0,2]]-[-9.437883451525,-1.0455166794],axis=2)
# Source body 2101579 is a connected aggregate of carrier and upper fixed frame.
# Finite manual envelope: lower carrier below the stationary upper supports,
# plus the outboard rising arm. Select whole existing triangles; no new surfaces.
body=z['unit_ids']==1
moving=body&((q[:,:,1].max(1)<=1143.5)|((rad.min(1)>=160)&(q[:,:,1].max(1)<=1300)))
# Keep central lower shaft/support, below the rotor's carrier attachment, fixed.
moving&=~((rad.max(1)<90)&(q[:,:,1].max(1)<1120))
# The radial envelope also catches disconnected pieces of the stationary top.
# Keep only its principal connected carrier; do not weld or alter source data.
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
before=moving.copy();selected=np.flatnonzero(moving)
_,vertex_alias=np.unique(np.round(p,5),axis=0,return_inverse=True)
tt=vertex_alias[tri[selected]];edges=np.concatenate([tt[:,[0,1]],tt[:,[1,2]],tt[:,[2,0]]])
_,labels=connected_components(coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(vertex_alias.max()+1,vertex_alias.max()+1)),directed=False)
parts=labels[tt[:,0]];ids,counts=np.unique(parts,return_counts=True);principal=ids[np.argmax(counts)]
moving[selected[parts!=principal]]=False
stray=np.flatnonzero(before&~moving)
assert moving.any() and (~moving).any()
w=GlbWriter('outpost/upper-motion-review',{'version':'2.0','generator':'source-motion review; original triangles, manual rigid grouping only'})
for uid in np.unique(z['unit_ids']):
 for role,mask in [('moving',(z['unit_ids']==uid)&moving),('context',(z['unit_ids']==uid)&~moving)]:
  ids=np.flatnonzero(mask)
  if not len(ids):continue
  t=tri[ids];used,inv=np.unique(t,return_inverse=True)
  w.add_node(f'outpost/fixed/upper-cluster/native-unit-{uid}/{role}',p[used]/1000,inv.reshape(-1,3),[str(z['palette'][int(k)]) or None for k in z['material_ids'][ids]],extras={'native_unit_index':int(uid),'source_unit_id':2101579 if uid==1 else None,'motion_review_role':role,'review_partition':True})
target=OUT/'outpost-upper-layer-review.glb';w.write(target)
d,b=read_glb(target);count=sum(len(t) for _,_,p,t,_ in mesh_instances(d,b));assert count==len(tri)
# Compare the complete triangle-position multiset after GLB float32 encoding.
def sig(q):
 a=np.asarray(q,dtype='<f4').reshape(len(q),9).copy();a=a[np.lexsort(a.T[::-1])];return hashlib.sha256(a.tobytes()).hexdigest()
original=(p[tri]/1000).astype('<f4');reopened=np.concatenate([pp[tt] for _,_,pp,tt,_ in mesh_instances(d,b)])
assert sig(original)==sig(reopened),'triangle coordinates changed'
inv=json.load(open(OUT/'analytic-inventory.json'));units=next(c['units']for c in inv['components']if c['id']=='base/source-model')
base={4072376,4077428,4568881,4570891,4594338,4756187,4764759,4770652,4773254}
# Central target-plate edge fasteners and guide-light mount details. Deliberately
# exclude long crossbar's repeated bolt rows (#4613501..#4616813).
base.update(u['source_id']for u in units if 4724429<=u['source_id']<=4726189 or 4764964<=u['source_id']<=4774144)
base.update([4606506,4606690,4607702,4607794,4607886,4608024,4608116,4608208,4608443,4608535])
assert base<={u['source_id']for u in units}
record={'status':'manual review candidate, not installed','outpost':{'input':str(src),'input_sha256':sha(src),'output':str(target),'output_sha256':sha(target),'source_body_id':2101579,'native_unit_index':1,'selected_triangles':int(moving.sum()),'stationary_top_triangles_restored':int(len(stray)),'original_triangles':len(tri),'complete_triangle_multiset_preserved':True,'selection':'finite manual source-coordinate carrier envelope; existing triangles only','needs_review':'Check the carrier/frame interface and outboard arm layers during rotation; not an actuator clearance certificate.'},'base_target':{'source_unit_ids':sorted(base),'status':'expanded candidate carriage with backing, side plates, fittings and lights; keep rail/end drives fixed','excluded_source_body_ids':[4268930,4275783,4558565]},'geometry_simplified':False}
np.savez_compressed(OUT/'outpost-carrier-triangle-selection.npz',selected_triangle_indices=np.flatnonzero(moving),stationary_top_triangle_indices=stray)
door=np.load(PIPE/'dart-station/door-candidate/native.npz');dp=door['positions_mm'][np.unique(door['triangles'])]
axis=np.array([0.,-np.cos(np.pi/12),np.sin(np.pi/12)])
floor_y=150.;platform_height=205.;closed_y=floor_y-platform_height
stroke=(closed_y-dp[:,1].max())/(-axis[1])
record['door_preview']={'source_pose':'open','floor_reference_product_y_mm':floor_y,'platform_height_mm':platform_height,'closed_bottom_product_y_mm':closed_y,'source_bottom_product_y_mm':float(dp[:,1].max()),'stroke_mm':float(stroke),'joint_coordinate_mm':[-float(stroke),0.],'status':'closed stop inferred from original source geometry and rulebook platform height, not measured actuator stop'}
record['cover_preview']={'status':'inspection motion only; real linkage uncalibrated','outward_mm':170.,'down_mm':45.,'source_body_ids':[4314593,4353403,4392221]}
(OUT/'layer-review.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record['outpost'],indent=2));print('Base candidate units',len(base))
