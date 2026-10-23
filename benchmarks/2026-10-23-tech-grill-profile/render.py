"""Software orthographic diagnostics; not runtime PBR/shadow equivalence."""
from build import *
import subprocess,tempfile
from PIL import Image,ImageDraw
spec=importlib.util.spec_from_file_location('raster',ROOT/'benchmarks/2026-10-17-base-panel-textures/review.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
def data(g):return (g,np.full((len(g),3),.252),np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),np.zeros(len(g),np.int32),np.zeros((1,1,3),np.uint8))
def main():
 s=np.load(REF);source=s['positions_mm'][s['triangles']][s['source_unit_ids']==1504356]/1000;q=np.load(OUT/'shell.npz');new=q['positions_mm'][q['triangles']]/1000;d,b=read_glb(BASE);rows=reader.extract(d,b);c=np.concatenate([x[3]for x in rows]);sel=np.load(OUT/'selection-ledger.npz')['selected_global_triangle_indices'];current=c[sel]/1000
 with tempfile.TemporaryDirectory() as td:
  tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
  for name,view in [('front',(.15,.2,1)),('reverse',(-.15,-.2,-1)),('edge',(1,.4,.25))]:
   canvas=Image.new('RGB',(1800,630),'#191919');draw=ImageDraw.Draw(canvas)
   for i,(label,g)in enumerate([('Source shell: 12926 triangles',source),('Current dark selection: 580 (heuristic)',current),('Extruded profiles: 2856 triangles',new)]):
    img=r.raster(data(g),source,view,helper,tmp,OUT/f'{name}-{i}.png');canvas.paste(Image.fromarray(img).resize((600,600)),(i*600,30));draw.text((i*600+8,8),label,fill='white')
   canvas.save(OUT/f'comparison-{name}.jpg')
if __name__=='__main__':main()
