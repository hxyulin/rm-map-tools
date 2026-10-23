import sys,importlib.util,json,tempfile,subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'out/rmuc2027-core-collision-manual';OUT.mkdir(exist_ok=True)
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review')]
def module(n,p):
 s=importlib.util.spec_from_file_location(n,ROOT/p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
f=module('focus','benchmarks/2026-10-23-visual-fidelity-review/render.py');import collision_review_render as r
ref=json.loads((ROOT/'out/rmuc2027-installed-reference-review/review.json').read_text())
source=Path(ref['roles']['collision']['assets']['tech-core']['path'])
placement=json.loads((ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json').read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0]
if __name__=='__main__':
 views=[]
 with tempfile.TemporaryDirectory()as td:
  tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
  for group in ['core-head','core-arm']:
   nodes=ref['targets'][group]['collision']['nodes'][:8]
   sheet=Image.new('RGB',(1600,800),'white');draw=ImageDraw.Draw(sheet)
   for k,n in enumerate(nodes):
    data=f.load(source,placement,{n['node']});im=Image.fromarray(r.raster(data,data[0],(1,.65,1),helper,tmp));im.save(OUT/f"node-{n['node']}.webp",lossless=True)
    thumb=im.resize((390,355));x=(k%4)*400;y=(k//4)*400;sheet.paste(thumb,(x,y+35));draw.text((x+8,y+9),f"node {n['node']} | {n['triangles']} tris",fill='black')
   sheet.save(OUT/(group+'-parts.jpg'))
