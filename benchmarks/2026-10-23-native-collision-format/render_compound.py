"""Three-cylinder preview; diagnostic tessellation is not the native format."""
import sys,copy,json,tempfile,subprocess
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'python'),str(ROOT/'benchmarks/2026-10-23-core-collision-manual')]
from inspect_parts import module,f,r,source,placement,ref
from build import revolve
from gltf_scene import read_glb,write_glb,accessor
from simplify_package import append_accessor,compact
OUT=ROOT/'out/rmuc2027-core-native-shapes';out=OUT/'compound';selection=json.loads((ROOT/'rules/collision-shapes-tech-core-compound-trial.json').read_text())
d,b=read_glb(source);ad=copy.deepcopy(d);blob=bytearray(b);ni=22;pr=d['meshes'][d['nodes'][ni]['mesh']]['primitives'][0];prims=[]
for s in selection['replacements'][0]['cylinders']:
 c=np.array(s['center_m'])*1000;a=np.array(s['axis_unit_vector']);radius=s['radius_m']*1000;length=s['length_m']*1000;segments=24
 g=revolve(c,a,[[-length/2,radius],[length/2,radius]],segments)
 u=np.cross(a,[0.,0,1]);u/=np.linalg.norm(u);v=np.cross(a,u);theta=np.arange(segments)*2*np.pi/segments;radial=np.cos(theta)[:,None]*u+np.sin(theta)[:,None]*v;caps=[]
 for sign in [-1,1]:
  center=c+sign*a*length/2;ring=center+radius*radial
  for i in range(segments):
   tri=np.array([center,ring[i],ring[(i+1)%segments]]);caps.append(tri if sign>0 else tri[::-1])
 g=np.concatenate([g,np.asarray(caps)]);normal=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None];cp=copy.deepcopy(pr);p=(g/1000).reshape(-1,3).astype(np.float32)
 cp['attributes']={'POSITION':append_accessor(ad,blob,p,'VEC3',5126),'NORMAL':append_accessor(ad,blob,np.repeat(normal,3,axis=0).astype(np.float32),'VEC3',5126)};cp['indices']=append_accessor(ad,blob,np.arange(len(p),dtype=np.uint32),'SCALAR',5125);cp['extras']={'inspection_only':True,'preview_of_native_cylinder':True};prims.append(cp)
ad['nodes'][ni]['mesh']=len(ad['meshes']);ad['meshes'].append({'primitives':prims});ad['asset'].setdefault('extras',{})['scope']='Native compound preview only; overlap surfaces are not a collision mesh replacement.'
preview=out/'preview.glb';write_glb(preview,ad,compact(ad,blob));records=[]
with tempfile.TemporaryDirectory()as td:
 tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
 for key,ids in [('joint',{22}),('arm',{n['node']for n in ref['targets']['core-arm']['collision']['nodes']})]:
  focus=np.concatenate([f.load(source,placement,ids)[0],f.load(preview,placement,ids)[0]])
  for view,di in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
   for stage,path in [('installed',source),('compound',preview)]:
    image=out/f'{key}-{view}-{stage}.webp';data=f.load(path,placement,ids);Image.fromarray(r.raster(data,focus,di,helper,tmp)).save(image,lossless=True);records.append(dict(key=key,view=view,stage=stage,path=str(image),direction=di,focus_bounds=[focus.min((0,1)).tolist(),focus.max((0,1)).tolist()]))
(OUT/'compound-renders.json').write_text(json.dumps(records,indent=2)+'\n')
