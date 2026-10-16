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
s=s.replace('full-partitions.png','depth-partitions.png')
exec(compile(s,'depth-preview','exec'))
