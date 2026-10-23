# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resolve diagnostic screenshot pixels to original source shell and current mesh."""
import json,sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review'))
import numpy as np
from gltf_scene import read_glb
spec=importlib.util.spec_from_file_location('fidelity_render',ROOT/'benchmarks/2026-10-23-visual-fidelity-review/render.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
OUT=ROOT/'out/rmuc2027-tech-bars-review'

def projected(g,reference,view=(1,.5,1)):
 f=np.array(view,float);f/=np.linalg.norm(f);right=np.cross([0,1,0],f);right/=np.linalg.norm(right);up=np.cross(f,right);frame=np.column_stack((right,up,f));b=reference@frame;lo,hi=b.min((0,1)),b.max((0,1));p=g@frame-(lo+hi)/2;scale=min(1140/(hi[0]-lo[0]),1140/(hi[1]-lo[1]));p[:,:,0]=p[:,:,0]*scale+600;p[:,:,1]=-p[:,:,1]*scale+600;return p

def pick(p,x,y):
 x+=.5;y+=.5;a=p[:,0];b=p[:,1];c=p[:,2];den=(b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0]);good=abs(den)>1e-10;den=np.where(good,den,1)
 u=((b[:,0]-x)*(c[:,1]-y)-(b[:,1]-y)*(c[:,0]-x))/den;v=((c[:,0]-x)*(a[:,1]-y)-(c[:,1]-y)*(a[:,0]-x))/den;w=1-u-v;ids=np.flatnonzero(good&(u>=0)&(v>=0)&(w>=0));z=u*p[:,0,2]+v*p[:,1,2]+w*p[:,2,2];return None if not len(ids) else int(ids[np.argmax(z[ids])])

def main():
 mapping=json.loads((ROOT/'out/rmuc2027-protected-source-reference/technology-core/tool-head/mapping.json').read_text());placement=json.loads((ROOT.parent/'rm-simulator/field-2027/equipment/manifest.json').read_text())['assets']['tech-core']['placements_in_source_arena_frame'][0]
 source=ROOT/mapping['reference_glb'];sd,sb=read_glb(source);s=r.load(source,placement,wrapper=mapping['runtime']['component_rest_matrix_m']);stagepaths={'source':source,'installed':ROOT.parent/'rm-simulator/field-2027/equipment/tech-core.glb','refined-1mm':ROOT/'out/rmuc2027-runtime-opportunities/refined/visual-1mm/tech-core.glb','protected-1mm':ROOT/'out/rmuc2027-visual-fidelity-review/protected-1mm/tech-core.glb'};out=[]
 points=[(190,340),(220,355),(255,374),(265,380),(220,375),(275,385),(240,360),(275,395),(205,360)]
 for name,path in stagepaths.items():
  doc,blob=read_glb(path)
  data=s if name=='source' else r.load(path,placement,r.select(path,'tech-core','technology-core/tool-head'));p=projected(data[0],s[0]);rows=[]
  for x,y in points:
   ti=pick(p,x,y)
   if ti is None:continue
   ni=int(data[4][ti]);node=doc['nodes'][ni]
   rows.append({'pixel':[x,y],'triangle':ti,'node':ni,'name':node['name'],'extras':node.get('extras',{}),'color':data[1][ti].tolist(),'vertices_render_m':data[0][ti].tolist()})
  out.append({'stage':name,'path':str(path),'picks':rows})
 (OUT/'trace.json').write_text(json.dumps(out,indent=2)+'\n')
 for a in out:
  print(a['stage'])
  for z in a['picks']:print(z['pixel'],z['name'],z['color'],z['extras'].get('source_unit_id'))
if __name__=='__main__':main()
