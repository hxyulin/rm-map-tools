from pathlib import Path
import sys,importlib.util,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image,ImageDraw
OUT=ROOT/'out/rmuc2027-tech-grill-panels'
spec=importlib.util.spec_from_file_location('raster',ROOT/'benchmarks/2026-10-17-base-panel-textures/review.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
s=np.load(ROOT/'out/rmuc2027-protected-source-reference/technology-core/tool-head/reference.npz');g=s['positions_mm'][s['triangles']]/1000;rgb=np.array([[float(v)for v in c.split(',')]for c in s['palette']])[s['material_ids']]
def data(g,c):return (g,c,np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),np.zeros(len(g),np.int32),np.zeros((1,1,3),np.uint8))
def main():
 selections=[('source',np.ones(len(g),bool)),*[(str(u),s['source_unit_ids']==u)for u in [1482927,1490076,1504356,1645179,1646257,1647370,1536323,1573248]]]
 with tempfile.TemporaryDirectory() as td:
  tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
  canvas=Image.new('RGB',(1500,1500),'#191919');draw=ImageDraw.Draw(canvas)
  for j,(label,m)in enumerate(selections):
   img=r.raster(data(g[m],rgb[m]),g,(.15,.2,1),helper,tmp,OUT/f'source-{label}.png');canvas.paste(Image.fromarray(img).resize((490,460)),((j%3)*500,(j//3)*500+35));draw.text(((j%3)*500+5,(j//3)*500+5),label,fill='white')
  canvas.save(OUT/'source-sheet.jpg')
if __name__=='__main__':main()

def compare():
 from build import extract,BASE
 from gltf_scene import read_glb
 q=np.load(OUT/'boundary-0.05mm/shell.npz');cg=q['positions_mm'][q['triangles']]/1000;cc=np.array([[float(v)for v in c.split(',')]for c in q['palette']])[q['material_ids']]
 d,b=read_glb(BASE);baseline=np.concatenate([r[3]for r in extract(d,b)])/1000;cl=np.load(OUT/'current-classification.npz');baseline=baseline[cl['selected_triangle_indices']]
 m=s['source_unit_ids']==1504356;stages=[('original',g[m],rgb[m]),('candidate',cg,cc),('current-heuristic',baseline,np.full((len(baseline),3),.252))]
 with tempfile.TemporaryDirectory() as td:
  tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
  canvas=Image.new('RGB',(1800,1260),'#191919');draw=ImageDraw.Draw(canvas)
  for vi,(view,v)in enumerate([('front',(.15,.2,1)),('reverse',(-.4,-.2,-1))]):
   for j,(label,geom,col)in enumerate(stages):
    img=r.raster(data(geom,col),g[m],v,helper,tmp,OUT/f'{label}-{view}.png');canvas.paste(Image.fromarray(img).resize((595,590)),(j*600,vi*630+35));draw.text((j*600+7,vi*630+7),f'{label} {view} / {len(geom)} triangles',fill='white')
  canvas.save(OUT/'comparison.jpg')
if __name__=='__main__':compare()
