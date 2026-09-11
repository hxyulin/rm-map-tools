"""Count the candidate, verify package pins and check base artwork occlusion."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from gltf_scene import read_glb, scene_nodes, mesh_instances
from simplify_package import scene_triangles, digest, check_bindings

root=Path('out/native-texture-candidate')
current=Path('../rm-simulator/local-assets/field')
report={'assets':{},'collision_unchanged':True}
for scope in ['', 'equipment']:
 before=json.loads((current/scope/'manifest.json').read_text())
 after=json.loads((root/scope/'manifest.json').read_text())
 bindings=json.loads((root/scope/after['articulation']['file']).read_text()) if after.get('articulation') else None
 if bindings: assert digest(root/scope/after['articulation']['file'])==after['articulation']['sha256']
 for name,entry in after['assets'].items():
  b=before['assets'][name]
  assert digest(root/scope/entry['collision'])==digest(current/scope/b['collision'])
  assert digest(root/scope/entry['visual'])==entry['visual_sha256']
  d,bin=read_glb(root/scope/entry['visual'])
  count=scene_triangles(d)
  assert count==entry['triangles'],(name,count,entry['triangles'])
  binding=bindings['assets'].get(name,{}).get('files',{}).get('visual') if bindings else None
  if binding:
   assert binding['sha256']==entry['visual_sha256'];check_bindings(d,binding)
  original,_=read_glb(current/scope/b['visual'])
  instances=max(1,len(entry.get('placements_in_source_arena_frame',[])))
  report['assets'][name]=dict(before=scene_triangles(original),after=count,instances=instances)
report['before']=sum(r['before']*r['instances'] for r in report['assets'].values())
report['after']=sum(r['after']*r['instances'] for r in report['assets'].values())
report['removed']=report['before']-report['after']
report['percent']=report['removed']/report['before']*100
# Sample opaque texels and find whether nearby backing triangles protrude through the patch.
s=json.loads((root/'equipment/texture-atlas.json').read_text())['files']['base.glb']
p=s['patches'][0]
d,b=read_glb(root/'equipment/base.glb')
ni=next(i for i,n in enumerate(d['nodes']) if n.get('name')==p['node'])
matrices={i:w for i,w,_ in scene_nodes(d)}
m=matrices[ni];c=np.asarray(p['corners_node_m'])@m[:3,:3].T+m[:3,3]
u=c[1]-c[0];v=c[3]-c[0];width=np.linalg.norm(u);height=np.linalg.norm(v);u/=width;v/=height;n=np.cross(u,v)
x,y,w,h=p['rect_px'];im=np.asarray(Image.open(root/'equipment'/s['pages'][p['page']]['file']))[y:y+h,x:x+w]
yy,xx=np.mgrid[0:h:4,0:w:4];opaque=im[yy,xx,3]>=128
samples=np.column_stack([xx[opaque]/(w-1)*width, yy[opaque]/(h-1)*height])
front=np.full(len(samples),-np.inf)
for index,pi,pts,tri,_ in mesh_instances(d,b):
 if 'TEXCOORD_0' in d['meshes'][d['nodes'][index]['mesh']]['primitives'][pi]['attributes']:continue
 projected=(pts-c[0])@np.column_stack([u,v,n]);t=projected[tri]
 mask=(t[:,:,2].min(1)<0.02)&(t[:,:,2].max(1)>-0.02)&(t[:,:,0].min(1)<=width)&(t[:,:,0].max(1)>=0)&(t[:,:,1].min(1)<=height)&(t[:,:,1].max(1)>=0)
 for a,bb,cc in t[mask]:
  e=bb[:2]-a[:2];f=cc[:2]-a[:2];den=e[0]*f[1]-e[1]*f[0]
  if abs(den)<1e-14:continue
  q=samples-a[:2];s1=(q[:,0]*f[1]-q[:,1]*f[0])/den;s2=(e[0]*q[:,1]-e[1]*q[:,0])/den
  inside=(s1>=0)&(s2>=0)&(s1+s2<=1)
  z=a[2]+s1*(bb[2]-a[2])+s2*(cc[2]-a[2]);valid=inside&(abs(z)<.02)
  front[valid]=np.maximum(front[valid],z[valid])
report['base_artwork_occlusion']=dict(samples=len(samples),occluded=int((front>0.0005+1e-6).sum()),max_backing_protrusion_m=float(front.max()) if np.isfinite(front.max()) else None)
(root/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
assert report['base_artwork_occlusion']['occluded']==0
