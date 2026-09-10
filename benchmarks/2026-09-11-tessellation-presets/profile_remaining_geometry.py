# SPDX-License-Identifier: MIT OR Apache-2.0
import json,struct
from pathlib import Path
root=Path('out/simulation-runtime');assets=[];nodes=[]
def inspect(path,static_only=False):
 b=path.read_bytes();g=json.loads(b[20:20+struct.unpack_from('<I',b,12)[0]])
 result=[]
 def walk(i,parents):
  n=g['nodes'][i];chain=parents+[n.get('name','')]
  if 'mesh' in n and (not static_only or 'static' in chain):
   count=sum((g['accessors'][p['indices']]['count'] if 'indices' in p else g['accessors'][p['attributes']['POSITION']]['count'])//3 for p in g['meshes'][n['mesh']]['primitives'] if p.get('mode',4)==4)
   result.append((n.get('name',''),count))
  for c in n.get('children',[]):walk(c,chain)
 for i in g['scenes'][g.get('scene',0)]['nodes']:walk(i,[])
 return result
for mf in ['manifest.json','equipment/manifest.json']:
 m=json.loads((root/mf).read_text())
 for name,a in m['assets'].items():
  n=max(1,len(a.get('placements_in_source_arena_frame',[])));v=inspect(root/Path(mf).parent/a['visual']);cfile=a['collision'] if a.get('collision_method')=='source-tessellation-v1' else a['visual'];c=inspect(root/Path(mf).parent/cfile,name in ['rune','outpost'])
  assets.append(dict(asset=name,instances=n,visual=n*sum(t for _,t in v),collider_input=n*sum(t for _,t in c)))
  for part,t in v:nodes.append(dict(asset=name,part=part,per_instance=t,placed=t*n))
result=dict(assets=sorted(assets,key=lambda a:-a['visual']),largest_visual_nodes=sorted(nodes,key=lambda a:-a['placed'])[:25])
Path('benchmarks/2026-09-11-tessellation-presets/remaining-geometry.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
