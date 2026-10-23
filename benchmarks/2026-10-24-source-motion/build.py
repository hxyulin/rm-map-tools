"""Build a source-bound motion identification sidecar; never modify CAD/meshes."""
from pathlib import Path
import json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/rmuc2027-source-motion'
def load(p):return json.loads((ROOT/p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
h=load('out/rmuc2027-hierarchy/hierarchy.json');a=load('out/rmuc2027-source-motion/analytic-inventory.json')
cs={c['id']:c for c in h['components']};units={u['source_id']:u for c in a['components'] for u in c['units']}
assert sha(ROOT/'source/RMUC2027_V1.0.0.stp')==h['source_sha256']
assert sha(ROOT/'out/rmuc2027-hierarchy/field.step')==h['files_sha256']['field.step']
joints=[]
def add(id,product,type,components=(),bodies=(),axis=None,origin=None,limits=None,**kw):
 assert all(c in cs and cs[c]['source_product_id']==product for c in components)
 assert all(b in units for b in bodies)
 if axis is not None: assert abs(np.linalg.norm(axis)-1)<1e-8
 uses=[]
 for o in h['source_occurrences']:
  if o['product_id']!=product:continue
  t=np.array(o['source_world_matrix']);r=t[:3,:3]
  uses.append({'source_occurrence_path':o['occurrence_path'],'source_world_matrix':t.tolist(),
   'world_axis':None if axis is None else (r@axis).tolist(),
   'world_origin_mm':None if origin is None else (r@origin+t[:3,3]).tolist()})
 joints.append(dict(id=id,source_product_id=product,type=type,component_ids=list(components),source_body_ids=list(bodies),axis_product_local=axis,origin_product_local_mm=origin,limits=limits,occurrences=uses,**kw))
# Exact original analytic surface supplies the axis line, not a fitted reduced mesh.
cyl=next(x for x in units[2101579]['cylinders'] if x['surface_id']==2010905)
add('outpost.rotor.spin',2603236,'continuous',[f'outpost/rotor/module-{i}' for i in range(3)],axis=[0,1,0],origin=cyl['point_mm'],
 status='source_axis_and_existing_rotor_membership',axis_witness=cyl,rule={'section':'5.6.1','printed_pages':[95,96],'steady_rad_s':float(.8*np.pi),'ramp_within_s':5,'teams_direction':'same per match'},fixed_components=[c for c in cs if c.startswith('outpost/fixed/')],review='Carrier/fastener ownership outside the three modules needs a source-level sweep review.')
rune_witness=next(x for x in units[161473]['cylinders'] if x['surface_id']==160752)
axis=np.array(rune_witness['axis']);axis=-axis/np.linalg.norm(axis);p=np.array(rune_witness['point_mm'])
other=max(units[83346]['cylinders'],key=lambda x:x['radius_mm'])
assert np.linalg.norm(np.cross(np.array(other['point_mm'])-p,axis))<1e-6
for bank in ['a','b']:
 add(f'rune.bank-{bank}.spin',1354629,'continuous',[f'rune/banks/bank-{bank}/arm-{i}' for i in range(5)]+[f'rune/banks/bank-{bank}/hub-cluster'],axis=axis.tolist(),origin=p.tolist(),status='source_common_axis_user_confirmed_arms_and_hub',coupling={'coordinate':'rune.common_angle','multiplier':1,'view_convention':'Opposite apparent clockwise sense when facing opposite sides; same signed angle around this common oriented axis.'},axis_witness=rune_witness,rule={'section':'5.6.3','printed_pages':[96,97]},stationary_source_unit_ids=[161473 if bank=='a' else 83346],review='User confirms center hub follows arms; central R-logo and shaft-end body remains stationary. Exclude the listed source unit from the selected hub component.')
for i,b in enumerate([4314593,4353403,4392221]):
 add(f'base.cover.{i}.open',4774244,'mechanism_unresolved',bodies=[b],status='main_cover_body_identified_motion_unresolved',rule={'section':'4.2.2','printed_pages':[37,38],'figures':['4-11','4-12']},legacy_reference='2026 outward/down slide was illustrative; 2027 installed 250 mm radial slide was also illustrative. Neither is adopted.',review='Determine linkage/trajectory and attached artwork/hardware before binding motion. No opening stroke or hinge fabricated.')
add('base.dart_target.slide',4774244,'prismatic',bodies=[4072376,4077428],axis=[1,0,0],limits={'unit':'mm','lower':-280,'upper':280,'zero':'source initial position'},status='axis_and_rule_limits_identified_carriage_partition_pending',rule={'section':'5.7.3','printed_pages':[110,111],'detector_and_guiding_light':'rigid relative pose'},fixed_source_body_ids=[4268930],review='Two central target/light bodies are candidate core selection, not complete carriage. Sensor fittings and source-surface-model details must be partitioned; rail/end drives stay fixed.')
rails=[units[b] for b in [3301978,3317722]]
edges=[max(u['long_edge_directions'],key=lambda x:x['length_mm']) for u in rails]
a0=np.array(edges[0]['axis']);a1=np.array(edges[1]['axis']);assert np.dot(a0,a1)>1-1e-10
add('dart_station.door.slide',3749800,'prismatic',['dart-station/door-candidate'],axis=a0.tolist(),status='source_guide_direction_identified_candidate_membership',axis_witnesses=edges,fixed_components=['dart-station/guide-rails','dart-station/frame'],rule={'section':'5.7.3','printed_pages':[109,110],'opening_duration_approx_s':7},review='Review door-candidate against fixed guide hardware. Stroke/end stops unknown; do not copy 2026 numeric origin or 1.16448 m illustrative stroke. Platform is a separate mechanism.')
# Keep manual review additions explicit and separate from whole-source-body selectors.
if (OUT/'layer-review.json').exists():
 layers=json.loads((OUT/'layer-review.json').read_text())
 for j in joints:
  if j['id']=='outpost.rotor.spin':j['manual_triangle_partition']=layers['outpost'];j['review']='Expanded carrier/arm layers need visual confirmation at the fixed-frame interface.'
  if j['id']=='base.dart_target.slide':j['candidate_source_unit_ids']=layers['base_target']['source_unit_ids'];j['review']='Expanded backing, brackets, fittings and light selection is a review candidate; rail/end drives excluded.'
  if j['id']=='dart_station.door.slide':j['inspection_preview']=layers['door_preview']
  if j['id'].startswith('base.cover.'):j['inspection_preview']=layers['cover_preview']
for j in joints:
 if j['id'].startswith('rune.') or j['id'] in ['base.dart_target.slide','dart_station.door.slide']:
  j['user_review']={'geometry_membership':'confirmed in visual preview','actuator_limits':'not certified by membership review'}
# Field width axis check for both Base placements, in original field coordinates.
for j in joints:
 if j['id']=='base.dart_target.slide':
  assert len(j['occurrences'])==2
  for o in j['occurrences']:assert abs(o['world_axis'][1])>1-1e-8
# Every selected whole component's source faces have one motion owner.
claimed=set()
for j in joints:
 faces={f for cid in j['component_ids'] for f in cs[cid]['face_ids']}
 assert not faces&claimed;claimed|=faces
pdf=Path('/Users/hxyulin/.t3/userdata/attachments/6657689a-5d3b-4bc0-9973-45db8c249b35-9221e06a-45fd-4ad8-9846-497cb2332856-pdf.pdf')
result={'schema_version':1,'kind':'source-motion-identification','runtime_ready':False,'geometry_modified':False,'source_sha256':h['source_sha256'],'hierarchy_sha256':sha(ROOT/'out/rmuc2027-hierarchy/hierarchy.json'),'coordinate_contract':'Original STEP product-local mm; use explicit occurrence matrices for field axes. Not glTF/FLU coordinates.','rulebook':{'file':pdf.name,'sha256':sha(pdf),'printed_page_to_pdf_page_offset':1},'legacy_references':{s:sha(ROOT/s) for s in ['rules/semantics-legacy-field.json','rules/semantics-legacy-equipment.json','rules/reviewed-motion-rmuc2027.json']},'joints':joints,'counts':{'mechanism_definitions':len(joints),'placed_mechanism_occurrences':sum(len(j['occurrences']) for j in joints)},'unresolved':['Base cover linkage, travel and attached details','Complete Base target carriage and fixed end hardware separation','Dart door candidate partition and stroke','Dart sliding platform is additional to requested door','Tech Core arm articulation is outside this requested scope; remains unresolved, not fixed']}
(OUT/'motions.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result['counts']));print('Source checksums, axis norms, guide parallelism, component ownership and Base field-width axes pass.')
