import json, shutil, hashlib
from pathlib import Path
from texture_atlas import export_atlas
from gltf_scene import read_glb
from simplify_package import read_config, run, scene_triangles
root=Path('out/atlas-simplification-comparison').resolve()
root.mkdir(exist_ok=False)
current=Path('../rm-simulator/local-assets/field').resolve()
installed=json.loads((current/'manifest.json').read_text())
old_report=json.loads((current/'mesh-simplification.json').read_text())
source=Path(old_report['input'])
source_copy=root/'source'
shutil.copytree(source,source_copy)
# Match the currently installed arena composition, which this preset passes through.
sm=json.loads((source_copy/'manifest.json').read_text())
for name in ['floor','arena-static','centre-platform','outpost-footing']:
 entry=installed['assets'][name]
 for kind in ['visual','collision']:
  shutil.copy2(current/entry[kind],source_copy/entry[kind])
 sm['assets'][name]=entry
(source_copy/'manifest.json').write_text(json.dumps(sm,indent=2))
# Verify that all geometry to be simplified is identical to the installed run's input.
for key, entry in old_report['assets'].items():
 scope,name=key.rsplit('/',1)
 manifest=json.loads((source_copy/scope/'manifest.json').read_text())
 for kind,data in entry.items():
  path=source_copy/scope/manifest['assets'][name][kind]
  assert hashlib.sha256(path.read_bytes()).hexdigest()==data['input_sha256'], (name,kind,'source changed')
rules=json.loads(Path('out/texture-atlas-grouped-preview/rules.json').read_text())
doc,_=read_glb(source_copy/'arena-static.glb')
live={n.get('name') for n in doc['nodes'] if 'mesh' in n}
selections=rules['files']['arena-static.glb']
missing=[s for s in selections if s['node'] not in live]
rules['files']['arena-static.glb']=[s for s in selections if s['node'] in live]
(root/'atlas-rules.json').write_text(json.dumps(rules,indent=2))
sidecar=export_atlas(source_copy,root/'atlas-rules.json')
config=installed['mesh_simplification']['settings'].copy()
config.update(input=str(source_copy),output=str(root/'simplified'))
(root/'simplify.json').write_text(json.dumps(config,indent=2))
print('Starting matched-source simplification',flush=True)
run(read_config(root/'simplify.json'))
def count(path):
 result={};total=0
 for scope in ['', 'equipment']:
  manifest=json.loads((path/scope/'manifest.json').read_text())
  for name,e in manifest['assets'].items():
   d,_=read_glb(path/scope/e['visual'])
   n=scene_triangles(d); instances=max(1,len(e.get('placements_in_source_arena_frame',[])))
   result[name]={'per_instance':n,'instances':instances,'placed':n*instances}
   total+=n*instances
 return {'placed_visual_triangles':total,'assets':result}
before=count(current);after=count(root/'simplified')
patches=sidecar['files']['arena-static.glb']['patches']
removed=sum(p['source_triangles'] for p in patches)
quads=2*len(patches)
result={'before':before,'after':after,'removed_artwork_triangles':removed,'patches':len(patches),'replacement_triangles':quads,'net_reduction':before['placed_visual_triangles']-after['placed_visual_triangles']-quads,'already_absent_selections':missing,'atlas_sections':len(rules['files']['arena-static.glb'])}
result['net_reduction_percent']=result['net_reduction']/before['placed_visual_triangles']*100
(root/'comparison.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2),flush=True)
