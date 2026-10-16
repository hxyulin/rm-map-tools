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
start=s.index('cases=[');end=s.index('\nfor slot',start)
s=s[:start]+"cases="+repr([('../module-0-cover-candidate/visual.glb','Outpost module candidate from -X','Source CAD colors',[-1,.15,.15]),('../module-0-cover-candidate/visual.glb','Outpost module candidate from +X','Source CAD colors',[1,.15,.15]),('outpost/full/visual.glb','Outpost full from -X','Source CAD colors',[-1,.15,.15]),('rune/components/banks/bank-a/arm-0/visual.glb','Rune arm close-up','Source CAD colors',[1,.15,.15])])+s[end:]
s=s.replace('full-partitions.png','depth-cover.png')
exec(compile(s,'depth-preview','exec'))
