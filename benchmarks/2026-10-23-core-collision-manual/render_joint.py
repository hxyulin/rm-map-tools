from inspect_parts import *
result=json.loads((OUT/'joint-cylinder.json').read_text());views=[]
with tempfile.TemporaryDirectory()as td:
 tmp=Path(td);helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
 for key,label,ids in [('joint','Solid-cylinder joint envelope',{22}),('joint-context','Joint envelope in arm context',{n['node']for n in ref['targets']['core-arm']['collision']['nodes']})]:
  focus=np.concatenate([f.load(source,placement,ids)[0],f.load(Path(result['candidate']),placement,ids)[0]])
  for view,di in [('oblique',(1,.65,1)),('reverse',(-1,.65,-1))]:
   for stage,p in [('installed',source),('candidate',Path(result['candidate']))]:
    path=OUT/f'{key}-{view}-{stage}.webp';data=f.load(p,placement,ids);Image.fromarray(r.raster(data,focus,di,helper,tmp)).save(path,lossless=True);views.append(dict(key=key,label=label,stage=stage,view=view,path=str(path),focus_nodes=sorted(ids),direction=di,focus_bounds=[focus.min((0,1)).tolist(),focus.max((0,1)).tolist()]))
(OUT/'joint-renders.json').write_text(json.dumps(views,indent=2)+'\n')
