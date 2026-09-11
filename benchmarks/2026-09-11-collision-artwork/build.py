"""Build stripped and simplified colliders while retaining installed visuals."""
import json,shutil
from pathlib import Path
import numpy as np
from collision_artwork import export_collision_artwork,strip
from gltf_scene import read_glb,mesh_instances
from simplify_package import digest
root=Path('out/collision-artwork-candidate').resolve()
current=Path('../rm-simulator/local-assets/field').resolve()
source=Path('out/tolerance-source').resolve()
shutil.copytree(current,root)
reports={}
for scope,name in [('', 'arena-static'),('equipment','base')]:
 base=root/scope;mp=base/'manifest.json';manifest=json.loads(mp.read_text());entry=manifest['assets'][name]
 if name=='base':
  original=json.loads((source/scope/'manifest.json').read_text())['assets'][name]
  original_path=source/scope/original['collision']
  assert digest(original_path)==original['collision_sha256']
  shutil.copy2(original_path,base/entry['collision'])
  for key in ['collision_sha256','collision_triangles']:entry[key]=original[key]
  entry.get('mesh_simplification',{}).pop('collision',None)
  entry['collision_method']='source-tessellation-v1'
  artpath=base/manifest['articulation']['file'];art=json.loads(artpath.read_text())
  art['assets'][name]['files']['collision']['sha256']=entry['collision_sha256']
  artpath.write_text(json.dumps(art,indent=2)+'\n');manifest['articulation']['sha256']=digest(artpath)
  mp.write_text(json.dumps(manifest,indent=2)+'\n')
 atlas=json.loads((base/'texture-atlas.json').read_text())['files'][entry['visual']]
 selections=[s for p in atlas['patches'] for s in (p.get('sources') or [dict(node=p['node'],material=p['material'])])]
 settings=dict(error_mm=4,sampled_limit_mm=8,deviation_samples=4096,lock_borders=False)
 if name=='arena-static':
  doc,binary=read_glb(base/entry['collision']);doc,binary,_=strip(doc,binary,selections)
  preserve=[]
  for ni,pi,points,_,_ in mesh_instances(doc,binary):
   q=points-points.mean(0);_,basis=np.linalg.eigh(q.T@q)
   if np.ptp(q@basis[:,0])<=.006:preserve.append(dict(node=doc['nodes'][ni]['name'],primitive=pi))
  settings['preserve']=preserve
 print('Processing',name,flush=True)
 reports[name]=export_collision_artwork(base,entry['visual'],selections,settings)
 print(name,reports[name]['before_triangles'],'->',reports[name]['after_triangles'],flush=True)
(root/'collision-artwork-report.json').write_text(json.dumps(reports,indent=2)+'\n')
