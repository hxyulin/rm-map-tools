# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Rasterize full exported inspection meshes without altering their geometry."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from gltf_scene import read_glb,mesh_instances
root=Path('local-assets/cad-components/rmuc2027/full-separation-v1')
W,H=1000,750;scale=2
font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',26)
small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',19)
canvas=Image.new('RGB',(W*2,H*2+100),'#f5f6f8');draw=ImageDraw.Draw(canvas)
draw.text((24,15),'Complete Rune / Outpost — original bodies and source shells',font=font,fill='#182334')
draw.text((24,55),'Full assembly views plus isolated parts. Native source geometry is preserved; these images use the exported inspection tessellation.',font=small,fill='#536072')
cases=[('outpost/full/visual.glb','Complete Outpost','6 components · 21,626 source faces',[-1,.4,1.3]),('rune/full/visual.glb','Complete Rune / Buff','13 components · 29,640 source faces',[1,.4,1.3]),('outpost/components/rotor/module-0/visual.glb','Complete Outpost module 0','5 solid bodies + 1 shell · 3,795 source faces',[-1,.2,1.1]),('rune/components/banks/bank-a/arm-0/visual.glb','Complete Rune arm candidate 0','10 solid bodies + 95 shells · 2,065 source faces',[1,.2,1.3])]
for slot,(file,title,note,view) in enumerate(cases):
 doc,binary=read_glb(root/file);chunks=[];all_points=[]
 forward=np.array(view,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward);right/=np.linalg.norm(right);up=np.cross(forward,right)
 basis=np.column_stack((right,up,forward))
 light=np.array([.4,.8,1.]);light/=np.linalg.norm(light)
 for ni,pi,p,t,mat in mesh_instances(doc,binary):
  tri=p[t];normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-14)
  rgb=np.array(doc['materials'][mat]['pbrMetallicRoughness']['baseColorFactor'][:3]);rgb=np.where(rgb<=.0031308,rgb*12.92,1.055*rgb**(1/2.4)-.055)
  brightness=.4+.6*np.abs(normals@light);colors=np.clip(rgb[None,:]*brightness[:,None]*255,0,255).astype('uint8')
  projected=tri@basis;chunks.append((projected,colors));all_points.append(p@basis)
 lo=np.min([p.min(0) for p in all_points],axis=0);hi=np.max([p.max(0) for p in all_points],axis=0);center=(lo+hi)/2
 factor=min((W*scale-100)/(hi[0]-lo[0]),((H-90)*scale-80)/(hi[1]-lo[1]))
 triangles=np.concatenate([p for p,c in chunks]);colors=np.concatenate([c for p,c in chunks]);depth=triangles[:,:,2].mean(1)
 xy=triangles[:,:,:2]-center[:2];xy[:,:,0]=xy[:,:,0]*factor+W*scale/2;xy[:,:,1]=-xy[:,:,1]*factor+(H-90)*scale/2
 xy=np.rint(xy).astype(np.int32);area=(xy[:,1,0]-xy[:,0,0])*(xy[:,2,1]-xy[:,0,1])-(xy[:,1,1]-xy[:,0,1])*(xy[:,2,0]-xy[:,0,0])
 order=np.argsort(depth);order=order[area[order]!=0]
 image=Image.new('RGB',(W*scale,(H-90)*scale),'#f5f6f8');raster=ImageDraw.Draw(image)
 for idx in order:
  a=xy[idx];raster.polygon([(int(a[0,0]),int(a[0,1])),(int(a[1,0]),int(a[1,1])),(int(a[2,0]),int(a[2,1]))],fill=tuple(int(c) for c in colors[idx]))
 image=image.resize((W,H-90),Image.Resampling.LANCZOS)
 x=(slot%2)*W;y=100+(slot//2)*H
 canvas.paste(image,(x,y+80));draw.text((x+25,y+10),title,font=font,fill='#182334');draw.text((x+25,y+45),note,font=small,fill='#536072')
 print(title,'triangles',len(triangles),'rasterized',len(order),flush=True)
 del binary,doc,chunks,triangles,colors,xy,order,all_points
canvas.save('local-assets/cad-audit/non-base/full-partitions.png')
