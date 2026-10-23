"""Reopen local collision trials and verify coverage, closure and exact ownership."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon
from shapely.ops import unary_union
from inventory import OUT,ROOT,hub,BINDINGS
from gltf_scene import read_glb,accessor,scene_nodes

def local_geometry(d,b,node):
 return [accessor(d,b,p['attributes']['POSITION'])[accessor(d,b,p['indices']).reshape(-1,3)].astype(float)*1000 for p in d['meshes'][d['nodes'][node]['mesh']]['primitives']]
def closed(g):
 _,inv=np.unique(g.reshape(-1,3),axis=0,return_inverse=True);f=inv.reshape(-1,3);edges=np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]);unique,counts=np.unique(np.sort(edges,axis=1),axis=0,return_counts=True);assert(counts==2).all()
 assert np.linalg.norm(np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]),axis=1).min()>1e-8
 return len(unique)
def main():
 proofs={};motion=json.loads(BINDINGS.read_text());stage=None
 for asset in ['outpost','rune']:
  r=json.loads((OUT/f'{asset}-verification.json').read_text());d,b=read_glb(Path(r['source_collision']));a,ab=read_glb(Path(r['candidate_collision']));_,_,source=hub.scan.load_nodes(Path(r['source_collision']));world={i:w for i,w,parent in scene_nodes(a)};rows=[]
  for row in r['records']:
   node=row['node'];proxy=local_geometry(a,ab,node)[-1];offset=0;pieces=[]
   for piece in row['pieces']:
    count=piece['proxy_triangles'];g=proxy[offset:offset+count];offset+=count;closed(g);w=world[node];geo=g@w[:3,:3].T+w[:3,3]*1000;original=source[node][piece['source_triangle_indices']]
    if asset=='outpost':
     eq=ConvexHull(geo.reshape(-1,3)).equations;error=float((original.reshape(-1,3)@eq[:,:3].T+eq[:,3]).max());assert error<1e-4
     reverse=hub.p.distances(hub.p.probes(geo,1000),original.reshape(-1,3),np.arange(len(original)*3).reshape(-1,3));piece['sampled_reverse_max_mm']=float(reverse.max())
     pieces.append(dict(kind=piece['kind'],source_faces=len(original),max_containment_plane_mm=error,sampled_reverse_max_mm=float(reverse.max())))
    else:
     center=np.array(piece['source_frame_center_mm']);axes=np.array(piece['source_frame_axes']);q=(geo-center)@axes.T;s=(original-center)@axes.T
     caprange=q[:,:,2].mean(1);caps=geo[(caprange>caprange.max()-.01)]
     capq=(caps-center)@axes.T;union=unary_union([Polygon(t[:,:2])for t in capq]);raw=unary_union([Polygon(t[:,:2])for t in s if Polygon(t[:,:2]).area>1e-8]);missing=raw.difference(union.buffer(.001)).area;assert missing<1e-4
     assert s[:,:,2].min()>q[:,:,2].min()+.09 and s[:,:,2].max()<q[:,:,2].max()-.09
     pieces.append(dict(kind=piece['kind'],source_faces=len(original),reopened_projection_missing_mm2=missing,reopened_source_thickness_margin_mm=min(s[:,:,2].min()-q[:,:,2].min(),q[:,:,2].max()-s[:,:,2].max()),sampled_reverse_max_mm=piece['sampled_reverse_max_mm']))
   assert offset==len(proxy)
   # Original retained primitive attributes/materials/indices and all node mounts are exact.
   old=d['meshes'][d['nodes'][node]['mesh']]['primitives'];new=a['meshes'][a['nodes'][node]['mesh']]['primitives'];j=0
   for selector in row['selectors']:
    p=old[selector['source_primitive']];idx=accessor(d,b,p['indices']).reshape(-1,3);keep=np.ones(len(idx),bool);keep[selector['selected_triangle_indices']]=False
    if not keep.any():continue
    q=new[j];j+=1;assert np.array_equal(idx[keep],accessor(a,ab,q['indices']).reshape(-1,3));assert p.get('material')==q.get('material')
    for k,v in p['attributes'].items():assert np.array_equal(accessor(d,b,v),accessor(a,ab,q['attributes'][k]))
   before=dict(d['nodes'][node]);after=dict(a['nodes'][node]);before.pop('mesh');after.pop('mesh');assert before==after
   groups=[i for i,m in enumerate(motion['rune_motion']if asset=='rune'else motion['outpost_motion'])if row['name']in m['bodies']]
   if asset=='rune':assert len(groups)==1
   rows.append(dict(node=node,component=row['component'],motion_groups=groups,pieces=pieces))
  for path,h in r['input_pins'].items():assert hub.scan.digest(Path(path))==h
  proofs[asset]=dict(owners=rows,source_faces_contained=sum(p['source_faces']for row in rows for p in row['pieces']),closed_solids=sum(len(row['pieces'])for row in rows),other_owners_exact=r['unchanged_other_mesh_owners_exact'],placed_triangles_saved=r['placed_triangles_saved'],max_sampled_reverse_mm=max(p['sampled_reverse_max_mm']for row in rows for p in row['pieces']))
  print(asset,'covered faces',proofs[asset]['source_faces_contained'],'solids',proofs[asset]['closed_solids'],'reverse sample max mm',proofs[asset]['max_sampled_reverse_mm'],flush=True)
 (OUT/'geometry-verification.json').write_text(json.dumps(proofs,indent=2)+'\n')
if __name__=='__main__':main()
