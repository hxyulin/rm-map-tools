# SPDX-License-Identifier: MIT OR Apache-2.0
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path('python').resolve()))
from validate_parts import read_part
from mesh_parts import tessellate_pair
from export_policy import ExportPolicy
parts=json.load(open('out/v12/parts.json'))['parts']
byname={p['name']:p for p in parts}
rows=[]
for asset,name in [('resource-zone','7000001_1_ASM'),('dart-station','0013_1_ASM'),('base','001_1_ASM')]:
 doc,rd,err=read_part(str(Path('out/v12')/byname[name]['file']))
 if err: raise RuntimeError(err)
 for preset in ['legacy','simulation','preview']:
  settings=ExportPolicy(preset).settings(asset,name);stats={};start=time.perf_counter()
  visual,collision=tessellate_pair(doc,settings,stats)
  record=dict(asset=asset,part=name,preset=preset,settings=settings,visual_triangles=len(visual[1]),collision_triangles=len(collision[1]),seconds=time.perf_counter()-start,stats=stats)
  rows.append(record);print(json.dumps(record),flush=True)
  Path('out/tessellation-benchmark/samples.json').write_text(json.dumps(rows,indent=2)+'\n')
