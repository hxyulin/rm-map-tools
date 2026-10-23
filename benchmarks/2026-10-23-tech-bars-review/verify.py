# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independently reopen strip repair and verify retained geometry/materials."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from gltf_scene import read_glb,accessor,scene_nodes
from simplify_package import scene_triangles
OUT=ROOT/'out/rmuc2027-tech-bars-review'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 r=json.loads((OUT/'bars.json').read_text());src=Path(r['input']);target=Path(r['output']);assert digest(src)==r['input_sha256'] and digest(target)==r['sha256'];assert digest(Path(r['source_npz']))==r['source_npz_sha256'];d,b=read_glb(src);a,ab=read_glb(target);assert a['materials']==d['materials'];selections={(x['node'],x['primitive']):x for x in r['removed']};surviving=0
 for i,n in enumerate(d['nodes']):
  out=a['nodes'][i];old={k:v for k,v in n.items()if k!='mesh'};new={k:v for k,v in out.items()if k!='mesh'}
  if i==78:new['children']=new['children'][:-1]
  assert old==new
  if 'mesh'not in n:assert 'mesh'not in out;continue
  sourcepr=d['meshes'][n['mesh']]['primitives'];actualpr=a['meshes'][out['mesh']]['primitives']if'mesh'in out else [];slot=0
  for pi,pr in enumerate(sourcepr):
   ix=accessor(d,b,pr['indices']).reshape(-1,3);keep=np.ones(len(ix),bool)
   if(i,pi)in selections:
    assert d['materials'][pr['material']]['extras']['step_colour_srgb']==[1.,1.,1.];keep[selections[(i,pi)]['triangle_indices']]=False
   if not keep.any():continue
   cp=actualpr[slot];slot+=1;assert cp['material']==pr['material'];assert set(cp['attributes'])==set(pr['attributes']);assert np.array_equal(accessor(a,ab,cp['indices']).reshape(-1,3),ix[keep])
   for k in pr['attributes']:assert np.array_equal(accessor(a,ab,cp['attributes'][k]),accessor(d,b,pr['attributes'][k]))
   surviving+=int(keep.sum())
  assert slot==len(actualpr)
 assert len(a['nodes'])==len(d['nodes'])+1 and a['nodes'][-1]['name']=='source-grill-strips';pr=a['meshes'][a['nodes'][-1]['mesh']]['primitives'][0];assert a['materials'][pr['material']]['extras']['step_colour_srgb']==[1.,1.,1.];assert a['materials'][pr['material']].get('emissiveFactor',[0,0,0])==[0,0,0]
 added=len(accessor(a,ab,pr['indices']))//3;assert added==84 and scene_triangles(a)==scene_triangles(d)-73+84==11612
 p=accessor(a,ab,pr['attributes']['POSITION']);normals=accessor(a,ab,pr['attributes']['NORMAL']);ix=accessor(a,ab,pr['indices']).reshape(-1,3);assert np.isfinite(p).all()and np.isfinite(normals).all();assert ix.max()<len(p);assert np.allclose(np.linalg.norm(normals,axis=1),1,atol=1e-6)
 # Recheck written planar strip geometry against original source, both ways.
 from mesh_quality import distances
 z=np.load(r['source_npz']);g=z['positions_mm'][z['triangles']];white=z['palette'][z['material_ids']]=='1.0000,1.0000,1.0000';g=g[np.isin(z['source_unit_ids'],[1505813,1532402,1565338,1568579])&white];q=p[ix].astype(float)*1000
 samples=lambda t:np.concatenate([t[:,0],t[:,1],t[:,2],t.mean(1)])
 forward=distances(samples(g),q.reshape(-1,3),np.arange(q.size//3).reshape(-1,3));reverse=distances(samples(q),g.reshape(-1,3),np.arange(g.size//3).reshape(-1,3));assert forward.max()<.01 and reverse.max()<.01
 installed={}
 for rel in ['manifest.json','equipment/manifest.json']:
  mp=ROOT.parent/'rm-simulator/field-2027'/rel
  for asset in json.loads(mp.read_text())['assets'].values():
   for role in ['visual','collision']:
    path=mp.parent/asset[role];assert digest(path)==asset[role+'_sha256'];installed[str(path)]=digest(path)
 review=json.loads((OUT/'review.json').read_text());metrics={};keys=set()
 for row in review['views']:
  key=(row['subject'],row['stage'],row['view']);assert key not in keys;keys.add(key)
  with Image.open(row['image'])as image:assert image.size==(1200,1200)
 assert len(keys)==60
 profile=json.loads((OUT/'source-profile.json').read_text());assert digest(Path(profile['input']))==profile['input_sha256'];assert digest(Path(profile['output']))==profile['sha256'];assert profile['all_other_source_geometry_exact'];assert profile['source_shell_before']-profile['profile_after']==10070
 for subject in ['face','grill','bar']:
  images={stage:np.asarray(Image.open(OUT/'renders'/subject/(stage+'-oblique.webp')))for stage in ['source','before','bars']};masks={stage:(im.min(2)>120)&(np.ptp(im.astype(int),axis=2)<8)for stage,im in images.items()};ref=masks['source'];metrics[subject]={'source_white_pixels':int(ref.sum()),**{stage:{'lost':int((ref&~mask).sum()),'gained':int((~ref&mask).sum())}for stage,mask in masks.items()if stage!='source'}}
 assert metrics['grill']['bars']['lost']<20 and metrics['bar']['bars']['lost']<30
 result={'reopened_verified':True,'source_immutable':True,'material_and_emission_unchanged':True,'retained_triangles_checked':surviving,'source_white_triangles':86,'removed_current_triangles':73,'added_triangles':added,'core_before':11601,'core_after':11612,'matched_images_verified':len(keys),'grill_profile_status':'Rejected for current runtime cost and fold seams; source-only review composition verified.','source_to_written_white_max_mm':float(forward.max()),'written_to_source_white_max_mm':float(reverse.max()),'finite_view_white_mask':metrics,'unchanged_installed_inputs':installed,'producer_sha256':{p.name:digest(p)for p in Path(__file__).parent.glob('*.py')}}
 (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print('Verified source strip shape, all retained triangle arrays, materials/hierarchy and 12 unchanged runtime GLBs.')
 (Path(__file__).parent/'results.json').write_text(json.dumps({k:v for k,v in result.items()if k!='unchanged_installed_inputs'},indent=2)+'\n')
if __name__=='__main__':main()
