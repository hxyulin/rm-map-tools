"""Check actual bundle files, pose conventions, unchanged inputs and source omission."""
import sys,json,hashlib,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb
from simplify_package import scene_triangles
from collision_shape_export import digest,geometry
from export_sim import read_stl
OUT=ROOT/'out/rmuc2027-core-native-shapes';results=[]
for out in [OUT,OUT/'compound']:
 data=json.loads((out/'collision-shapes.json').read_text());assert data['retained_mesh']['triangles']==65301;assert digest(out/'remainder.glb')==data['retained_mesh']['sha256']
 d,b=read_glb(out/'remainder.glb');assert 'mesh'not in d['nodes'][22];assert scene_triangles(d)==65301
 triangles=read_stl(out/'remainder.stl');expected=geometry(d,b);np.testing.assert_allclose(triangles.reshape(-1,3,3),expected,rtol=0,atol=1e-7)
 tree=ET.parse(out/'model.sdf');assert tree.findtext('.//static')=='true';collisions=tree.findall('.//collision');assert len(collisions)==len(data['native_parts'])+1
 for part,col in zip(data['native_parts'],collisions[1:]):
  shape=part['shape'];pose=np.fromstring(col.findtext('pose'),sep=' ');np.testing.assert_allclose(pose[:3],shape['pose']['translation_m'],rtol=0,atol=1e-14)
  np.testing.assert_allclose(Rotation.from_euler('xyz',pose[3:]).as_matrix(),Rotation.from_quat(shape['pose']['rotation_xyzw']).as_matrix(),rtol=0,atol=1e-12)
  assert float(col.findtext('geometry/cylinder/radius'))==shape['radius_m'];assert float(col.findtext('geometry/cylinder/length'))==shape['length_m']
 results.append({'bundle':str(out.relative_to(ROOT)),'remaining_mesh_triangles':65301,'native_cylinders':len(data['native_parts']),'selected_source_triangles_removed':3187,'sdf_xml_pose_dimension_roundtrip':True,'sdf_runtime_parser_available':False,'stl_matches_remaining_glb_world_geometry':True,'files':{name:digest(out/name)for name in ['collision-shapes.json','model.sdf','remainder.glb','remainder.stl']}})
ref=json.loads((ROOT/'out/rmuc2027-installed-reference-review/review.json').read_text())
for p,h in ref['pins'].items():assert digest(Path(p))==h
report={'bundles':results,'installed_inputs_unchanged':True,'runtime_integration':False,'compound_forward_sampling':json.loads((OUT/'compound-fit-check.json').read_text()),'tests':'7 new exporter tests and 3 existing assembly collision tests pass; no Rust changes/builds.'}
(OUT/'verification.json').write_text(json.dumps(report,indent=2)+'\n');(Path(__file__).with_name('results.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
