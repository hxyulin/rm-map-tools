"""Seven matched whole-arena source-color views from the complete original STEP."""
import sys,json,importlib.util,subprocess,shutil,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from PIL import Image
from plan_cad_lods import digest
from gltf_scene import read_glb,scene_nodes,accessor
OUT=ROOT/'out/rmuc2027-full-source-field-review'
def module(name,path):
 sp=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
runtime=module('runtime','benchmarks/2026-10-23-runtime-opportunities/render.py');raster=module('raster','benchmarks/2026-10-17-base-panel-textures/review.py');metrics=raster.metrics
VIEWS=[('oblique',(1,1.2,1)),('reverse',(-1,1.2,-1)),('top',(0,1,.000001)),('front',(0,.000001,1)),('back',(0,.000001,-1)),('side',(1,.000001,0)),('bottom',(0,-1,.000001))]
def main():
 source=json.loads((OUT/'source.json').read_text());assert digest(Path(source['reference']))==source['sha256']
 guardpath=ROOT/'out/rmuc2027-visual-fidelity-review/guard.json';guard=json.loads(guardpath.read_text());(OUT/'guard-snapshot.json').write_text(json.dumps(guard,indent=2)+'\n')
 refined=json.loads((ROOT/'out/rmuc2027-runtime-opportunities/refined.json').read_text());package=ROOT.parent/'rm-simulator/field-2027';placements={}
 for path in (package/'manifest.json',package/'equipment/manifest.json'):
  for name,a in json.loads(path.read_text())['assets'].items():placements[name]=a['placements_in_source_arena_frame']
 stages={'original-full-native':[('full-source',Path(source['reference']),[])],'refined1mm':[],'combined17mm':[],'protected-current':[]}
 for name,r in guard['assets'].items():
  baseline=ROOT/'out/rmuc2027-runtime-opportunities'/refined['assets'][name+'/visual']['output'];assert digest(baseline)==refined['assets'][name+'/visual']['sha256']
  combined=Path(r['input']);protected=Path(r['output']);assert digest(combined)==r['input_sha256'];assert digest(protected)==r['sha256']
  for stage,path in [('refined1mm',baseline),('combined17mm',combined),('protected-current',protected)]:stages[stage].append((name,path,placements[name]))
 tmp=OUT/'raster-work';tmp.mkdir(exist_ok=True);helper=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
 report={'scope':'Complete original STEP-derived native tessellation vs accepted refined1mm, combined17mm input and pinned current protected override; whole-arena source-color and embedded-texture flat two-sided orthographic diagnostics, no runtime PBR.','source_coverage':{k:source[k] for k in ('source_sha256','summary','original_source_face_ids_exactly_partitioned','placed_triangles','mapping_limit')},'guard_sha256':digest(guardpath),'stages':{},'views':[],'camera':{'size':[1200,1200],'padding_pixels':30,'frame':'source Z up transformed to diagnostic Y up: (x,z,-y)','projection':'orthographic; camera direction points from scene toward viewer; common original source bounds center and scale per view','lighting':'two-sided abs(normal dot normalized(forward + .8 up - .3 right)); .55 ambient + .45 diffuse'}}
 reference=None
 for stage,inputs in stages.items():
  data,owners=runtime.load_stage(inputs);n=len(data[0]);assert n==(source['placed_triangles'] if stage=='original-full-native' else sum(sum(d['accessors'][p['indices']]['count']//3 for i,_,_ in scene_nodes(d) if 'mesh' in d['nodes'][i] for p in d['meshes'][d['nodes'][i]['mesh']]['primitives'])*max(1,len(pl)) for _,path,pl in inputs for d in [read_glb(path)[0]]))
  if reference is None:
   # Bounding-box corners yield identical projected extrema to the complete geometry only for axis views. Retain exact hull-extrema per view below.
   reference=data[0];bounds={}
   for name,direction in VIEWS:
    f=np.array(direction,float);f/=np.linalg.norm(f);r=np.cross([0,1,0],f);r/=np.linalg.norm(r);u=np.cross(f,r);frame=np.column_stack((r,u,f));p=reference@frame;lo=p.min((0,1));hi=p.max((0,1));bounds[name]={'direction':direction,'projected_min_m':lo.tolist(),'projected_max_m':hi.tolist(),'pixel_scale_per_m':float(min(1140/(hi[0]-lo[0]),1140/(hi[1]-lo[1]))),'frame_columns_right_up_forward':frame.tolist()}
   report['camera']['views']=bounds
   # Exact extrema witnesses suffice to fix the same camera without retaining 8M triangles for subsequent stages.
   witnesses=[]
   flat=reference.reshape(-1,3)
   for _,direction in VIEWS:
    f=np.array(direction,float);f/=np.linalg.norm(f);r=np.cross([0,1,0],f);r/=np.linalg.norm(r);u=np.cross(f,r)
    for axis in (r,u,f):
     proj=flat@axis;witnesses.extend([flat[proj.argmin()],flat[proj.argmax()]])
   reference=np.array(witnesses).reshape(-1,3,3)
  report['stages'][stage]={'placed_triangles':n,'files':[{'asset':name,'path':str(path),'sha256':digest(path),'placements':pl} for name,path,pl in inputs]}
  folder=OUT/'renders';folder.mkdir(exist_ok=True)
  for name,direction in VIEWS:
   target=folder/f'{stage}-{name}.webp';img=raster.raster(data,reference,direction,helper,tmp,tmp/'frame.png');Image.fromarray(img).save(target,lossless=True)
   record={'stage':stage,'view':name,'image':str(target),'triangles':n}
   if stage!='original-full-native':record['versus_original']=metrics.metric(np.asarray(Image.open(folder/f'original-full-native-{name}.webp')),img)
   report['views'].append(record);print(stage,name,n,flush=True)
  del data,owners;gc.collect()
 for inputs in stages.values():
  for _,path,_ in inputs:assert digest(path)==next(f['sha256'] for s in report['stages'].values() for f in s['files'] if f['path']==str(path))
 report['producer_sha256']=digest(Path(__file__));(OUT/'renders.json').write_text(json.dumps(report,indent=2)+'\n');print('COMPLETE',flush=True)
if __name__=='__main__':main()
