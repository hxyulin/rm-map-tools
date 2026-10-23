# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only curve scope trials; source geometry is the comparison authority."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'python'),str(Path(__file__).parent)]
from curve import *
from gltf_scene import *

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def geometry(d,b,node):
 pr=d['meshes'][d['nodes'][node]['mesh']]['primitives'][0];p=accessor(d,b,pr['attributes']['POSITION']).astype(float)*1000;t=accessor(d,b,pr['indices']).reshape(-1,3);return p[t]
def side(g,axis,anchor,lo,hi,rmin):
 m=select(g,axis,anchor,lo,hi,rmin);a,u,v=frame(axis);x=g-anchor;ang=np.unwrap(np.arctan2(x@v,x@u),axis=1);m &= np.ptp(ang,axis=1)<.5
 n=np.cross(g[:,1]-g[:,0],g[:,2]-g[:,0]);c=g.mean(1)-anchor;rad=c-np.outer(c@a,a);nr=(n*rad).sum(1)/np.maximum(np.linalg.norm(n,axis=1)*np.linalg.norm(rad,axis=1),1e-30);m &= nr>.15
 return m

def run():
 report=json.load(open(ROOT/'out/rmuc2027-runtime-opportunities/refined.json'));results=[]
 configs=[('arm-cylinder', 'technology-core/arm-and-shared',1,0,[0,1,0],[-100,0,84],78.5,70),('arm-elbow', 'technology-core/arm-and-shared',18,0,[-.3420201433,0,.9396926208],[-10.95,-571.8,-160.66],78.5,70),('arm-wrist','technology-core/arm-and-shared',26,0,[0,-1,0],[-615.12,0,-317.71],40.99,35),('shoulder-round','technology-core/pedestal-and-shoulder',15,1,[0,1,0],[-100,0,84],109,90)]
 for role in ['visual','collision']:
  source=ROOT.parent/'rm-simulator/field-2027/equipment'/('tech-core'+('-collision' if role=='collision' else '')+'.glb');row=report['assets']['tech-core/'+role];baseline=ROOT/'out/rmuc2027-runtime-opportunities'/row['output'];sd,sb=read_glb(source);bd,bb=read_glb(baseline)
  scopes={}; source_nodes={}
  for i,w,par in scene_nodes(sd):
   e=sd['nodes'][i].get('extras',{}); scopes[i]=e.get('component_id') or e.get('composition_occurrence',{}).get('component_id') or scopes.get(par)
   sh=e.get('native_shell_index',e.get('source_native_shell_index'))
   if sh is not None and 'mesh' in sd['nodes'][i]: source_nodes[scopes[i],sh]=i
  for name,cid,shell,group,axis,anchor,radius,rmin in configs:
   nodes=[source_nodes[cid,shell]] if (cid,shell) in source_nodes else []
   rec={'name':name,'role':role,'component':cid,'source':str(source.resolve()),'source_sha256':digest(source),'baseline':str(baseline.resolve()),'baseline_sha256':digest(baseline),'source_nodes':nodes,'native_shell':shell,'axis':axis,'anchor_mm':anchor,'radius_mm':radius,'trials':[]};results.append(rec)
   if len(nodes)!=1:rec['reason']='ambiguous or absent source shell';continue
   sg=geometry(sd,sb,nodes[0]);a,*_=frame(axis);heights=(sg-anchor)@a;lo=float(heights.min());hi=float(heights.max());sm=side(sg,axis,anchor,lo,hi,rmin);sourcepatch=sg[sm];child=1672+group;cg=geometry(bd,bb,child);cm=side(cg,axis,anchor,lo,hi,rmin)
   # Scope attribution: only faces entirely within the source shell's 1.2 mm
   # sampled neighbourhood can enter a patch in the merged material group.
   ids=np.flatnonzero(cm)
   if len(ids):
    dd=distances(surface_samples(cg.reshape(-1,3),np.arange(len(cg)*3).reshape(-1,3))[ids].reshape(-1,3),sg.reshape(-1,3),np.arange(len(sg)*3).reshape(-1,3)).reshape(-1,7).max(1);cm[ids[dd>1.2]]=False
   rec.update(source_patch_triangles=int(sm.sum()),baseline_patch_triangles=int(cm.sum()),baseline_node=child,lo_mm=lo,hi_mm=hi,rmin_mm=rmin)
   if sm.sum()<3 or cm.sum()<3:rec['reason']='insufficient eligible curved patch';continue
   rec['baseline_boundary_edges']=len(boundaries(cg[cm]))
   for sectors in [1,4,8,12,16,24]:
    tr={'sectors':sectors};rec['trials'].append(tr)
    try:
     q,meta=retriangulate(cg[cm],axis=axis,anchor=anchor,radius=radius,sectors=sectors);tr.update(meta);tr['triangles']=len(q);tr['saving_per_scene']=int(cm.sum()-len(q));tr['boundary']=boundary_error(cg[cm],q)
     if tr['boundary']['maximum_sampled_boundary_mm']>.01:tr['rejected']='patch boundary not preserved'
     if len(q)>=cm.sum():tr['rejected']='not cheaper than refined1mm';continue
     out=np.concatenate([cg[~cm],q]);forward=distances(samples(sourcepatch,1),out.reshape(-1,3),np.arange(len(out)*3).reshape(-1,3));reverse=distances(samples(q,1),sg.reshape(-1,3),np.arange(len(sg)*3).reshape(-1,3));tr['source_to_output_mm']=float(forward.max());tr['output_to_source_mm']=float(reverse.max());tr['max_mm']=float(max(forward.max(),reverse.max()));tr['accepted_1mm']=tr['max_mm']<=1.2 and not tr.get('rejected');tr['accepted_4mm_exception']=tr['max_mm']<=4 and not tr.get('rejected');tr['samples']=len(forward)+len(reverse)
    except Exception as e:tr['rejected']=str(e)
   print(name,role,'source',sm.sum(),'baseline',cm.sum(),[(t.get('triangles'),round(t.get('max_mm',999),2),t.get('rejected')) for t in rec['trials']],flush=True)
 (ROOT/'out/rmuc2027-curve-trial/tech-experiments.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':run()
