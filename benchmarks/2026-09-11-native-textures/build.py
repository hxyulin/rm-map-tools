"""Build a local native-texture candidate without replacing simulator assets."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
from texture_atlas import export_atlas

root=Path('out/native-texture-candidate').resolve()
current=Path('../rm-simulator/local-assets/field').resolve()
source=Path('out/tolerance-source').resolve()
shutil.copytree(current,root)
# Arena input is the installed, unsimplified arena, including composition fixes.
config=json.loads(Path('out/texture-atlas-grouped-preview/rules.json').read_text())
config.update(render_mode='embedded',normal_hint=[0,0,1],simplify={'arena-static.glb':dict(error_mm=4,
 sampled_limit_mm=12,deviation_samples=4096,lock_borders=False,preserve_planar_m=0.006)})
(root/'arena-atlas-rules.json').write_text(json.dumps(config,indent=2))
print('Simplifying arena backing',flush=True)
export_atlas(root,root/'arena-atlas-rules.json')
# Restore only the base visual from its pinned unsimplified input.
equipment=root/'equipment'
manifest=json.loads((equipment/'manifest.json').read_text())
original=json.loads((source/'equipment/manifest.json').read_text())['assets']['base']
entry=manifest['assets']['base']
shutil.copy2(source/'equipment'/original['visual'],equipment/entry['visual'])
for key in ['visual_sha256','triangles']:
 entry[key]=original[key]
entry.get('mesh_simplification',{}).pop('visual',None)
artpath=equipment/manifest['articulation']['file']
art=json.loads(artpath.read_text())
art['assets']['base']['files']['visual']['sha256']=entry['visual_sha256']
artpath.write_text(json.dumps(art,indent=2)+'\n')
manifest['articulation']['sha256']=hashlib.sha256(artpath.read_bytes()).hexdigest()
(equipment/'manifest.json').write_text(json.dumps(manifest,indent=2))
config=dict(schema_version=1,render_mode='embedded',pixels_per_metre=4096,atlas_size=2048,
 merge_distance_m=0,files={'base.glb':[dict(node='source_13267588_001_1_1',material='colour_1.0000,1.0000,1.0000')]},
 simplify={'base.glb':dict(error_mm=4,sampled_limit_mm=12,deviation_samples=4096,lock_borders=False)})
(root/'base-atlas-rules.json').write_text(json.dumps(config,indent=2))
print('Simplifying base backing',flush=True)
export_atlas(equipment,root/'base-atlas-rules.json')
print('Native texture candidate complete',flush=True)
