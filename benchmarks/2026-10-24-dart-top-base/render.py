"""Matched full-frame and station context for Dart side profiles."""
import json,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from export import ROOT,OUT,hub,local_geometry
from gltf_scene import read_glb
ref=hub.p.module('dart_profile_raster_helpers',str(ROOT/'benchmarks/2026-10-23-rune-profile-r3/trial.py'));raster=ref.raster

def data(nodes,ids,record,stage):
 node=record['node'];ids=sorted(i for i in ids if i in nodes);geos=[];colors=[]
 for i in ids:
  g=nodes[i];color=np.tile([.58,.60,.63],(len(g),1))
  if i==node:
   if stage=='source':
    mask=np.concatenate([*[np.isin(np.arange(sel['source_triangles']),sel['selected_triangle_indices'])for sel in record['selectors']],np.zeros(record['retained_side_triangles'],bool)]);color[mask]=[.16,.63,.84]
   else:color[(record['retained_original_triangles']+record['retained_side_triangles']):]=[.77,.42,.19]
  geos.append(g);colors.append(color)
 g=np.concatenate(geos)*.001@np.array([[1,0,0],[0,0,-1],[0,1,0]]);return(g,np.concatenate(colors),np.zeros((len(g),3,2)),np.zeros(len(g),np.int32),np.zeros(len(g),np.int32),np.zeros((1,1,3),np.uint8))

def main():
 r=json.loads((OUT/'verification.json').read_text());d,c,source=hub.scan.load_nodes(Path(r['source_collision']));_,_,target=hub.scan.load_nodes(Path(r['candidate_collision']));rows=[];basis=np.array([[1,0,0],[0,0,-1],[0,1,0]])
 with tempfile.TemporaryDirectory()as tmp:
  tmp=Path(tmp)
  for record in r['records']:
   node=record['node'];rotation=np.array(record['world_matrix'])[:3,:3];sign=1 if source[node].mean((0,1))[0]>0 else-1
   for scope in ['frame','top','base']:
    ids={node};datasets={stage:data(geometry,ids,record,stage)for stage,geometry in [('source',source),('candidate',target)]}
    if scope!='frame':
     for stage,path in [('source',r['source_collision']),('candidate',r['candidate_collision'])]:
      doc,blob=read_glb(Path(path));local=np.concatenate(local_geometry(doc,blob,node));mask=local[:,:,1].max(1)<-1000 if scope=='top' else local[:,:,1].min(1)>-400
      ds=datasets[stage];datasets[stage]=tuple(v[mask]if hasattr(v,'shape')and len(v)==len(mask)else v for v in ds)
    frame=np.concatenate([a[0]for a in datasets.values()])
    for view,localdir in [('oblique',[1,-.6,1]),('side',[1,0,0]),('end',[0,0,1])]:
     direction=np.array(localdir)@rotation.T@basis
     for stage,a in datasets.items():
      path=OUT/f'node{node}-{scope}-{view}-{stage}.webp';Image.fromarray(raster.raster(a,frame,direction,ROOT/'out/rmuc2027-conservative-shape-audit/raster',tmp)).save(path,lossless=True);rows.append(dict(node=node,scope=scope,view=view,stage=stage,path=str(path),sha256=hub.scan.digest(path)))
   print('Rendered',node,flush=True)
 (OUT/'renders.json').write_text(json.dumps(dict(views=rows,note='Source side triangles blue, replacement profile triangles orange. Retained geometry and station context grey. All visual bytes unchanged.'),indent=2)+'\n')
if __name__=='__main__':main()
