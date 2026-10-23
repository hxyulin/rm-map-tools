"""Reopen source/candidate and verify exact retained data and whole-face coverage."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from export import OUT,hub,local_geometry,covered_by
from gltf_scene import read_glb,accessor
r=json.loads((OUT/'verification.json').read_text());d,b=read_glb(Path(r['source_collision']));a,ab=read_glb(Path(r['candidate_collision']));rows=[]
for row in r['records']:
 node=row['node'];groups=local_geometry(d,b,node);source=np.concatenate(groups[:-1]);mask=np.concatenate([np.isin(np.arange(s['source_triangles']),s['selected_triangle_indices'])for s in row['selectors']]);selected=source[mask];newgroups=local_geometry(a,ab,node);proxy=newgroups[-1];covered=np.zeros(len(selected),bool);pieces=[]
 assert np.array_equal(groups[-1],newgroups[-2]),'Accepted slimmer side geometry changed'
 for i,piece in enumerate(row['pieces']):
  geo=proxy[12*i:12*(i+1)];vertices,inv=np.unique(geo.reshape(-1,3),axis=0,return_inverse=True);assert len(vertices)==8
  f=inv.reshape(-1,3);edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1);assert(np.unique(edges,axis=0,return_counts=True)[1]==2).all()
  covered|=covered_by(selected,vertices);pieces.append(dict(label=piece['label'],kind=piece['kind'],closed=True))
 assert len(proxy)==12*len(row['pieces']);assert covered.all(),int((~covered).sum())
 old=d['meshes'][d['nodes'][node]['mesh']]['primitives'];new=a['meshes'][a['nodes'][node]['mesh']]['primitives'];j=0
 for s in row['selectors']:
  p=old[s['source_primitive']];indices=accessor(d,b,p['indices']).reshape(-1,3);keep=np.ones(len(indices),bool);keep[s['selected_triangle_indices']]=False
  if not keep.any():continue
  q=new[j];j+=1;assert np.array_equal(indices[keep],accessor(a,ab,q['indices']).reshape(-1,3))
  assert p.get('material')==q.get('material')
  for k,v in p['attributes'].items():assert np.array_equal(accessor(d,b,v),accessor(a,ab,q['attributes'][k]))
 # Side payload arrays, material and original metadata match exactly.
 assert old[-1].get('material')==new[-2].get('material')
 for k,v in old[-1]['attributes'].items():assert np.array_equal(accessor(d,b,v),accessor(a,ab,new[-2]['attributes'][k]))
 before=dict(d['nodes'][node]);after=dict(a['nodes'][node]);before.pop('mesh');after.pop('mesh');assert before==after
 rows.append(dict(node=node,source_faces_contained=len(selected),retained_original_faces_exact=row['retained_original_triangles'],accepted_side_faces_exact=len(groups[-1]),closed_boxes=len(pieces),pieces=pieces))
for path,h in r['input_pins'].items():assert hub.scan.digest(Path(path))==h
report=dict(records=rows,candidate_sha256=hub.scan.digest(Path(r['candidate_collision'])),source_faces_contained=sum(x['source_faces_contained']for x in rows),closed_boxes=sum(x['closed_boxes']for x in rows),other_owners_exact=r['unchanged_mesh_owners_exact'],installed=False)
(OUT/'geometry-verification.json').write_text(json.dumps(report,indent=2)+'\n');print('Verified',report['source_faces_contained'],'complete selected faces enclosed;',report['closed_boxes'],'closed boxes; sides and retained data exact.')
