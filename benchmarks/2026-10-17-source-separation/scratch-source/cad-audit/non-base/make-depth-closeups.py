# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
from pathlib import Path
s=Path('local-assets/cad-audit/non-base/render-full-partitions.py').read_text()
s=s.replace('import sys,json','import sys,json,subprocess,struct')
a=s.index(' xy=np.rint(xy)');b=s.index(' image=image.resize',a)
s=s[:a]+''' triangles[:,:,:2]=xy
 records=np.empty(len(triangles),dtype=[('p','<f4',(3,3)),('c','u1',(3,))]);records['p']=triangles;records['c']=colors
 temp=Path('local-assets/cad-audit/non-base/raster-input.bin');output=temp.with_suffix('.ppm')
 with temp.open('wb') as stream:
  stream.write(struct.pack('<iii',W*scale,(H-90)*scale,len(triangles)));stream.write(records.tobytes())
 subprocess.run(['local-assets/cad-audit/non-base/depth-raster',str(temp),str(output)],check=True)
 image=Image.open(output)
 order=triangles
''' + s[b:]
s=s.replace("('outpost/full/visual.glb','Complete Outpost','6 components · 21,626 source faces',[-1,.4,1.3])", "('outpost/full/visual.glb','Outpost opposite side','Depth-tested source tessellation',[1,.2,-1.3])")
s=s.replace("('rune/full/visual.glb','Complete Rune / Buff','13 components · 29,640 source faces',[1,.4,1.3])", "('rune/components/banks/bank-a/arm-0/visual.glb','Rune arm reverse','Depth-tested source tessellation',[-1,.2,-1.3])")
s=s.replace("'5 solid bodies + 1 shell · 3,795 source faces',[-1,.2,1.1]", "'Front side — original source geometry',[1,.2,-1.1]")
s=s.replace('full-partitions.png','depth-closeups.png')
exec(compile(s,'depth-preview','exec'))
