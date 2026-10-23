# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compose a source-only profile review without guessing merged runtime ownership."""
import copy,json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from gltf_scene import read_glb,write_glb,accessor
from simplify_package import append_accessor,compact,scene_triangles
OUT=ROOT/'out/rmuc2027-tech-bars-review'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 path=ROOT/'out/rmuc2027-protected-source-reference/technology-core/tool-head/reference.glb';profile=ROOT/'out/rmuc2027-tech-grill-profile/shell.npz';d,b=read_glb(path);changed=copy.deepcopy(d);binary=bytearray(b);node=next(i for i,n in enumerate(d['nodes'])if n.get('extras',{}).get('source_unit_id')==1504356);old=d['meshes'][d['nodes'][node]['mesh']]['primitives'];assert len(old)==1;material=old[0]['material'];assert d['materials'][material]['extras']['step_colour_srgb']==[.252,.252,.252]
 z=np.load(profile);g=z['positions_mm'][z['triangles']]/1000;p=g.reshape(-1,3).astype(np.float32);n=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);n/=np.linalg.norm(n,axis=1)[:,None];pr={'attributes':{'POSITION':append_accessor(changed,binary,p,'VEC3',5126),'NORMAL':append_accessor(changed,binary,np.repeat(n,3,axis=0).astype(np.float32),'VEC3',5126)},'indices':append_accessor(changed,binary,np.arange(len(p),dtype=np.uint32),'SCALAR',5125),'material':material};changed['nodes'][node]['mesh']=len(changed['meshes']);changed['nodes'][node]['extras']['profile_review']=True;changed['meshes'].append({'name':'source-grill-profile-review','primitives':[pr]});changed['asset'].setdefault('extras',{})['inspection_only']=True
 blob=compact(changed,binary);target=OUT/'source-profile.glb';write_glb(target,changed,blob);a,ab=read_glb(target);assert a['materials']==d['materials'];assert len(a['nodes'])==len(d['nodes'])
 for i,n in enumerate(d['nodes']):
  if i==node:continue
  assert {k:v for k,v in a['nodes'][i].items()if k!='mesh'}=={k:v for k,v in n.items()if k!='mesh'}
  if'mesh'not in n:continue
  sp=d['meshes'][n['mesh']]['primitives'];ap=a['meshes'][a['nodes'][i]['mesh']]['primitives'];assert len(sp)==len(ap)
  for s,t in zip(sp,ap):
   assert s['material']==t['material'];assert set(s['attributes'])==set(t['attributes']);assert np.array_equal(accessor(d,b,s['indices']),accessor(a,ab,t['indices']))
   for k in s['attributes']:assert np.array_equal(accessor(d,b,s['attributes'][k]),accessor(a,ab,t['attributes'][k]))
 before=scene_triangles(d);after=scene_triangles(a);assert before-after==12926-len(g)
 r={'input':str(path),'input_sha256':digest(path),'profile':str(profile),'profile_sha256':digest(profile),'output':str(target),'sha256':digest(target),'before_source_head_triangles':before,'after_source_head_triangles':after,'selected_source_shell':1504356,'source_shell_before':12926,'profile_after':len(g),'all_other_source_geometry_exact':True,'scope':'Source-to-profile visual study; standalone source head, not runtime replacement or faster-than-current claim. 34 structural slots and 70 bores retained, 2mm thickness, sharp slot corners and hexagonal bores approximate source curves.'};(OUT/'source-profile.json').write_text(json.dumps(r,indent=2)+'\n');print(before,'->',after,'source shell12926->',len(g))
if __name__=='__main__':main()
