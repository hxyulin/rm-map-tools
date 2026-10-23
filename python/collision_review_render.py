# SPDX-License-Identifier: MIT OR Apache-2.0
"""Matched orthographic collision review raster; no baseline selection or geometry writes."""
import hashlib,struct,subprocess
import numpy as np
from PIL import Image

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def raster(data,reference,direction,helper,tmp,near_plane=False):
    g,colours,uv,textured,_,texture=data;width=height=1800
    forward=np.asarray(direction,float);forward/=np.linalg.norm(forward)
    right=np.cross([0,1,0],forward)
    if np.linalg.norm(right)<1e-6:right=np.array([1.,0,0])
    right/=np.linalg.norm(right);up=np.cross(forward,right);frame=np.column_stack((right,up,forward))
    p=g@frame;bounds=reference@frame;lo,hi=bounds.min((0,1)),bounds.max((0,1));p-=(lo+hi)/2
    scale=min((width-90)/max(hi[0]-lo[0],1e-9),(height-90)/max(hi[1]-lo[1],1e-9))
    p[:,:,0]=p[:,:,0]*scale+width/2;p[:,:,1]=-p[:,:,1]*scale+height/2
    normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-20)
    light=forward+.8*up-.3*right;light/=np.linalg.norm(light)
    shade=.55+.45*abs(normal@light);rgb=np.clip(colours*shade[:,None]*255,0,255).astype('uint8')
    records=np.empty(len(g),dtype=[('p','<f4',(3,3)),('c','u1',(3,)),('uv','<f4',(3,2)),('textured','<i4'),('shade','<f4')])
    records['p']=p;records['c']=rgb;records['uv']=uv;records['textured']=textured;records['shade']=shade
    with (tmp/'input.bin').open('wb')as f:
        f.write(struct.pack('<iiiii',width,height,len(g),texture.shape[1],texture.shape[0]))
        f.write(texture.tobytes());f.write(records.tobytes())
    command=[str(helper),str(tmp/'input.bin'),str(tmp/'image.ppm'),str(tmp/'owners.bin')]
    if near_plane:command.append(str((hi[2]-lo[2])/2+.15))
    subprocess.run(command,check=True)
    return np.asarray(Image.open(tmp/'image.ppm')).copy()
