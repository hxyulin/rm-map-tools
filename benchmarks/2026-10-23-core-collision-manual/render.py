from inspect_parts import *
result=json.loads((OUT/'result.json').read_text());candidate=Path(result['candidate']);records=[]
with tempfile.TemporaryDirectory()as td:
 tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
 for key,label,ids in [('tube','Arm flanged tube',{17}),('sleeve','Head threaded sleeve',{1284}),('arm','Complete arm scope',{x['node']for x in ref['targets']['core-arm']['collision']['nodes']}),('head','Complete head scope',{x['node']for x in ref['targets']['core-head']['collision']['nodes']})]:
  focus=f.load(source,placement,ids)[0]
  for view,di in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
   for stage,p in [('installed',source),('candidate',candidate)]:
    data=f.load(p,placement,ids);path=OUT/f'{key}-{view}-{stage}.webp';Image.fromarray(r.raster(data,focus,di,helper,tmp)).save(path,lossless=True)
    records.append(dict(key=key,label=label,view=view,stage=stage,path=str(path),focus_nodes=sorted(ids),direction=di,focus_bounds=[focus.min((0,1)).tolist(),focus.max((0,1)).tolist()]))
for p,h in ref['pins'].items():assert r.digest(Path(p))==h
(OUT/'renders.json').write_text(json.dumps(records,indent=2)+'\n')
