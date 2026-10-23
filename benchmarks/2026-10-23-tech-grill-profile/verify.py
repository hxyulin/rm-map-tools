"""Roundtrip, topology, source-distance and open-aperture checks."""
from build import *
from gltf_scene import read_glb_nodes
from mesh_quality import distances

def samples(g):return np.concatenate([g.mean(1),g[:,0],g[:,1],g[:,2],(g[:,0]+g[:,1])/2])
def main():
 report=json.loads((OUT/'report.json').read_text());npz=np.load(OUT/'shell.npz');original=npz['positions_mm'][npz['triangles']];rows=list(read_glb_nodes(OUT/'shell.glb'));panels=[]
 for (name,p,t,col),rec in zip(rows,report['planes']):
  g=p[t]*1000;v,ix=np.unique(np.round(g.reshape(-1,3),4),axis=0,return_inverse=True);top=mesh_metrics(v,ix.reshape(-1,3));assert top['closed_oriented_manifold'] and top['signed_volume_mm3']>0
  o=np.array(rec['origin_mm']);b=np.array(rec['basis_rows']);n=np.array(rec['normal']);height=(g-o)@n;mask=np.max(abs(height),axis=1)<.0002;uv=(g[mask]-o)@b.T;v,ix=np.unique(np.round(uv.reshape(-1,2),6),axis=0,return_inverse=True);ix=ix.reshape(-1,3);edges=np.sort(np.concatenate([ix[:,[0,1]],ix[:,[1,2]],ix[:,[2,0]]]),axis=1);e,ct=np.unique(edges,axis=0,return_counts=True);dom=sh.build_area(sh.multilinestrings(v[e[ct==1]]))
  assert dom.geom_type=='Polygon' and len(dom.interiors)==len(rec['apertures'])
  # The aperture polygons themselves, reconstructed from the actual GLB cap, must
  # preserve all source witnesses and almost all source hole area after float32 export.
  s=np.load(REF);sg=s['positions_mm'][s['triangles']];src,so,sb,_,_=reader.domain(sg[s['source_face_ids']==rec['source_face_pair'][0]])
  holes=[sh.Polygon(r)for r in dom.interiors];ap=[]
  for h in src.interiors:
   old=sh.Polygon(h);matched=min(holes,key=lambda q:q.centroid.distance(old.centroid));assert matched.covers(old.representative_point());occluded=old.difference(matched).area;assert occluded<.01
   ap.append({'source_area_mm2':old.area,'roundtrip_source_area_occluded_mm2':occluded,'roundtrip_boundary_hausdorff_mm':sh.hausdorff_distance(old.boundary,matched.boundary,densify=.1)})
  panels.append({'source_face_pair':rec['source_face_pair'],'roundtrip_triangles':len(g),'roundtrip_topology':top,'aperture_count':len(holes),'aperture_checks':ap})
 reopened=np.concatenate([p[t]*1000 for _,p,t,_ in rows]);s=np.load(REF);source=s['positions_mm'][s['triangles']][s['source_unit_ids']==1504356]
 def deviation(a,b):
  x=distances(samples(a),b.reshape(-1,3),np.arange(b.size//3).reshape(-1,3));return {'max_mm':float(x.max()),'p99_mm':float(np.percentile(x,99)),'sample_count':len(x)}
 result={'panels':panels,'source_to_candidate_sampled':deviation(source,reopened),'candidate_to_source_sampled':deviation(reopened,source),'glb_roundtrip_sampled':deviation(reopened,original),'visual_inspection':'Front, reverse, edge software orthographic views: structural slots remain open; existing broad diagonal artifacts absent in this flat-surface diagnostic. Thin bright fold seams visible between independent extruded panels; reject for final use pending joined-fold construction. This diagnostic does not validate runtime lighting/shadows.','final_decision':'Reject for integration: 2856 triangles exceeds current585; approximate fold joints visibly split; centroid mask unsafe.','source_sha256_unchanged':digest(REF)==report['source_sha256'],'bars_restored_sha256_unchanged':digest(BASE)==report['bars_restored_sha256']}
 assert result['source_sha256_unchanged'] and result['bars_restored_sha256_unchanged'];(OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print({k:v for k,v in result.items()if k!='panels'})
if __name__=='__main__':main()
