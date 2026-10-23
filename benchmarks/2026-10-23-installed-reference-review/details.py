import review as q
import json,tempfile,subprocess
from pathlib import Path
from PIL import Image
s=json.loads((q.OUT/'review.json').read_text())
with tempfile.TemporaryDirectory() as td:
 tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(q.ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
 for v in s['views']:
  t=s['targets'][v['target']];row=s['roles'][v['role']]['assets'][t['asset']];p=Path(row['path']);ps=q.placements[t['asset']]['placements_in_source_arena_frame']
  data=q.fidelity.load(p,(ps or [{}])[0],set(v['focus_nodes']))
  path=q.OUT/(v['target']+'-'+v['role']+'-'+v['view']+'-isolated.webp')
  Image.fromarray(q.r.raster(data,data[0],v['camera_direction'],helper,tmp)).save(path,lossless=True)
  v['isolated_path']=str(path);v['isolated_sha256']=q.digest(path)
for p,h in s['pins'].items():assert q.digest(Path(p))==h
(q.OUT/'review.json').write_text(json.dumps(s,indent=2)+'\n')
