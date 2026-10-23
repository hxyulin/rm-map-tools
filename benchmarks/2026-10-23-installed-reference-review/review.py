"""Pin installed inputs and render local density targets, without simplifying geometry."""
import sys, json, hashlib, shutil, importlib.util, tempfile, subprocess
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out/rmuc2027-installed-reference-review'; OUT.mkdir(exist_ok=True)
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'benchmarks/2026-10-23-visual-fidelity-review')]
from gltf_scene import read_glb,scene_nodes,accessor

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
loader=mod('installed_loader','benchmarks/2026-10-23-runtime-opportunities/render.py')
import collision_review_render as r
fidelity=mod('installed_focus','benchmarks/2026-10-23-visual-fidelity-review/render.py')
from simplify_package import scene_triangles
audit=json.loads((ROOT/'benchmarks/2026-10-23-runtime-opportunities/results.json').read_text())
placements={};origins={};pins={}
for rel in ['manifest.json','equipment/manifest.json','rmuc2027-bindings.json']:
 p=ROOT.parent/'rm-simulator/field-2027'/rel;pins[str(p)]=digest(p)
 if p.name=='manifest.json':
  entries=json.loads(p.read_text())['assets'];placements.update(entries);origins.update({k:p.parent for k in entries})
targets=[('core-head','Tech Core head','tech-core','technology-core/tool-head'),('core-arm','Tech Core arm','tech-core','technology-core/arm-and-shared'),('dart-deck','Dart deck / hardware','arena-static','dart-station/deck-and-shared-hardware'),('dart-frame','Dart frame','arena-static','dart-station/frame')]
summary={'reference':'Installed simulator assets; new manual investigation starting point. Earlier conservative checkpoint retained as comparison only.','pins':pins,'roles':{},'targets':{},'views':[]}
for role in ['visual','collision']:
 inputs=[];assets={}
 for asset,entry in placements.items():
  source=origins[asset]/entry[role];known=audit['assets'][asset+'/'+role];assert digest(source)==known['sha256']
  row={'path':str(source),'sha256':known['sha256'],'placements':max(1,len(entry['placements_in_source_arena_frame'])),'scene_triangles':scene_triangles(read_glb(source)[0]),'placed_triangles':known['placed_triangles']}
  assert row['scene_triangles']*row['placements']==row['placed_triangles'];pins[str(source)]=row['sha256']
  p=OUT/'reference'/role/(asset+'.glb');p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():assert digest(p)==row['sha256']
  else:shutil.copyfile(source,p)
  assets[asset]={**row,'path':str(p),'installed_path':str(source)}
  inputs.append((asset,p,placements[asset]['placements_in_source_arena_frame']))
 summary['roles'][role]={'assets':assets,'placed_triangles':sum(x['placed_triangles']for x in assets.values())}
 data,owners=loader.load_stage(inputs)
 assert len(data[0])==summary['roles'][role]['placed_triangles']
 with tempfile.TemporaryDirectory()as td:
  tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
  for key,label,asset,component in targets:
   p=Path(assets[asset]['path']);doc,blob=read_glb(p);inherited={};nodes=[]
   for ni,world,parent in scene_nodes(doc):
    node=doc['nodes'][ni];inherited[ni]=node.get('extras',{}).get('component_id',inherited.get(parent,asset))
    if 'mesh'not in node or inherited[ni]!=component:continue
    count=sum(len(accessor(doc,blob,pr['indices']))//3 for pr in doc['meshes'][node['mesh']]['primitives'])
    nodes.append({'node':ni,'name':node.get('name'),'triangles':count,'extras':node.get('extras',{})})
   nodes.sort(key=lambda x:-x['triangles']);assert nodes
   summary['targets'].setdefault(key,{'label':label,'asset':asset,'component':component})[role]={'placed_triangles':sum(n['triangles']for n in nodes)*assets[asset]['placements'],'nodes':nodes}
   # Review complete Core scopes, or densest Dart member where both stations share the same component ID.
   ids={n['node']for n in nodes} if asset=='tech-core' else {nodes[0]['node']}
   ps=placements[asset]['placements_in_source_arena_frame'];focus=fidelity.load(p,(ps or [{}])[0],ids)[0]
   for view,di in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
    path=OUT/(key+'-'+role+'-'+view+'.webp')
    Image.fromarray(r.raster(data,focus,di,helper,tmp)).save(path,lossless=True)
    summary['views'].append({'target':key,'role':role,'view':view,'path':str(path),'camera_direction':di,'focus_nodes':sorted(ids),'focus_bounds':[focus.min((0,1)).tolist(),focus.max((0,1)).tolist()],'sha256':digest(path)})
    print(key,role,view,flush=True)
for p,h in pins.items():assert digest(Path(p))==h
(OUT/'review.json').write_text(json.dumps(summary,indent=2)+'\n')
print('Verified installed inputs unchanged; totals',[(r,v['placed_triangles'])for r,v in summary['roles'].items()],flush=True)
