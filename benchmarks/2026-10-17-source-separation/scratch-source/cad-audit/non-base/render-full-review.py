# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Depth-tested inspection renders of complete CAD assemblies, source rest poses."""
import sys,json,struct,hashlib,gzip,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
from gltf_scene import read_glb,mesh_instances
out=Path('local-assets/cad-audit/full-model-review');out.mkdir(exist_ok=True)
base=Path('local-assets/cad-components/rmuc2027/full-separation-v1')
package=Path('../rm-map-tools/out/rm2027/packages/rmuc2027')
manifest=json.loads((package/'manifest.json').read_text())
W,H=1400,1200;scale=2;report=[]
def load_gz(path):
 data=gzip.decompress(path.read_bytes());n,k=struct.unpack_from('<II',data,12);doc=json.loads(data[20:20+n]);off=20+n;length,kind=struct.unpack_from('<II',data,off)
 return doc,data[off+8:off+8+length],hashlib.sha256(data).hexdigest()
def geometry(name):
 chunks=[];inputs=[]
 if name!='base':
  file=base/name/'full/visual.glb';doc,binary=read_glb(file)
  inputs.append({'file':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
  sources=[(doc,binary,np.eye(4))]
 else:
  sources=[]
  to_yup=np.array([[1.,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]])
  for asset in ['base','base-footing']:
   file=package/'models'/f'{asset}.glb.gz';doc,binary,digest=load_gz(file)
   assert doc['asset']['extras']['source_sha256']==manifest['source_sha256']
   inputs.append({'file':str(file),'compressed_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'uncompressed_sha256':digest})
   place=np.array(manifest['assets'][asset]['placements_in_source_arena_frame'][0]['matrix_local_to_arena'])
   sources.append((doc,binary,to_yup@place))
 for doc,binary,matrix in sources:
  for ni,pi,p,t,mat in mesh_instances(doc,binary):
   p=p@matrix[:3,:3].T+matrix[:3,3];tri=p[t]
   rgb=np.array(doc['materials'][mat]['pbrMetallicRoughness']['baseColorFactor'][:3]);rgb=np.where(rgb<=.0031308,rgb*12.92,1.055*rgb**(1/2.4)-.055)
   chunks.append((tri,rgb))
 return chunks,inputs
for name,views in [('outpost',[[-1,.3,1.25],[1,.3,-1.25]]),('rune',[[1,.3,1.3],[-1,.3,-1.3]]),('base',[[1,.55,1.4],[-1,.55,-1.4]])]:
 chunks,inputs=geometry(name)
 triangles=np.concatenate([t for t,c in chunks]);rgb=np.concatenate([np.broadcast_to(c,(len(t),3)) for t,c in chunks]);del chunks
 normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-20)
 for index,view in enumerate(views):
  forward=np.array(view,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward);right/=np.linalg.norm(right);up=np.cross(forward,right);basis=np.column_stack((right,up,forward))
  projected=triangles@basis;lo=projected.min((0,1));hi=projected.max((0,1));center=(lo+hi)/2
  factor=min((W*scale-160)/(hi[0]-lo[0]),(H*scale-160)/(hi[1]-lo[1]))
  projected-=center;projected[:,:,0]=projected[:,:,0]*factor+W*scale/2;projected[:,:,1]=-projected[:,:,1]*factor+H*scale/2
  light=(forward+.8*up-.3*right);light/=np.linalg.norm(light);brightness=.55+.45*np.abs(normals@light)
  colors=np.clip(rgb*brightness[:,None]*255,0,255).astype('uint8')
  records=np.empty(len(triangles),dtype=[('p','<f4',(3,3)),('c','u1',(3,))]);records['p']=projected;records['c']=colors
  temp=out/'raster-input.bin';output=out/'raster-output.ppm'
  with temp.open('wb') as stream:stream.write(struct.pack('<iii',W*scale,H*scale,len(triangles)));stream.write(records.tobytes())
  subprocess.run(['local-assets/cad-audit/non-base/depth-raster',str(temp),str(output)],check=True)
  image=Image.open(output);image.resize((W,H),Image.Resampling.LANCZOS).save(out/f'{name}-{index+1}.png');image.close()
  print(name,index+1,len(triangles),'triangles',flush=True)
 report.append({'model':name,'triangles':len(triangles),'inputs':inputs,'views':views,'render':'per-pixel orthographic depth; 2x supersampling; source RGB, illustrative shading; original rest pose'})
 del triangles,rgb,normals,projected,records
for file in ['raster-input.bin','raster-output.ppm']:(out/file).unlink()
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
