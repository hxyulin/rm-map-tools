# SPDX-License-Identifier: MIT OR Apache-2.0
"""Count selected-scene triangles and ask the simulator for actual static colliders."""
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from gltf_scene import read_glb
from simplify_package import scene_triangles
root=Path(__file__).resolve().parents[2]
report={}
packages={'deployed':root.parent/'rm-simulator/local-assets/field'}
packages.update({n:root/'out'/('tolerance-'+n) for n in ('control','moderate','aggressive','coarse')})
packages.update({n:root/'out'/n for n in ('checked-moderate','checked-aggressive','checked-coarse')})
for name,path in packages.items():
    assets={};total=0;size=0
    for scope in ('','equipment'):
        m=json.loads((path/scope/'manifest.json').read_text())
        for key,a in m['assets'].items():
            d,_=read_glb(path/scope/a['visual']);n=scene_triangles(d)
            count=max(1,len(a['placements_in_source_arena_frame']))
            assets[key]=dict(visual_per_instance=n,placements=count)
            total+=n*count
            size+=sum((path/scope/a[k]).stat().st_size for k in ('visual','collision'))
    result=subprocess.run([str(root.parent/'rm-simulator/target/debug/examples/inspect_assets'),str(path)],capture_output=True,text=True,check=True)
    Path(__file__).with_name(name+'-inspect.log').write_text(result.stdout+result.stderr)
    colliders=sum(int(n) for n in re.findall(r'(\d+) (?:ground|fixture|equipment) triangles',result.stdout))
    report[name]=dict(visual=total,static_colliders=colliders,glb_bytes=size,assets=assets)
    print(name,total,colliders,size,flush=True)
Path(__file__).with_name('counts.json').write_text(json.dumps(report,indent=2)+'\n')
