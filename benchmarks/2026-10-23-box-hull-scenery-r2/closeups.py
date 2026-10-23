"""Face-aligned views of one small mounting strip and its end details."""
import importlib.util,json,tempfile,subprocess
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('scenery_render_closeup',Path(__file__).with_name('render.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def main():
    row=next(r for r in json.loads((m.OUT/'adaptive.json').read_text())if r['node']==354 and r['island']==5 and r['proof']['inward_envelope_limit_mm']==.5)
    _,_,nodes=m.original.load_nodes(row['source']);g=nodes[354][row['source_triangle_indices']]
    p=np.asarray(row['hull_vertices_mm']);cg=p[ConvexHull(p).simplices]
    _,_,vt=np.linalg.svd(p-p.mean(0),full_matrices=False)
    frame=np.array([[1,0,0],[0,0,-1],[0,1,0]])
    face=vt[-1]@frame;oblique=(vt[-1]+.35*vt[1]+.1*vt[0])@frame
    longitudinal=(g.mean(1)-p.mean(0))@vt[0]
    subset=g[longitudinal>longitudinal.max()-28]
    views=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        if not helper.is_file():
            helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for scope,focus in [('member',g),('end-detail',subset)]:
            reference=m.old.data(focus,[.6,.6,.6])[0]
            for direction,name in [(face,'face'),(oblique,'oblique')]:
                for stage,data in [('source',m.colored(g,np.arange(len(g)))),('proxy',m.colored(cg,np.arange(len(cg)),(.18,.65,.85)))]:
                    path=m.OUT/f'dart-strip-{scope}-{name}-{stage}.webp'
                    Image.fromarray(m.r.raster(data,reference,direction,helper,tmp)).save(path,lossless=True)
                    views.append(dict(scope=scope,view=name,stage=stage,path=str(path),sha256=m.original.digest(path)))
    (m.OUT/'closeups.json').write_text(json.dumps(views,indent=2)+'\n')


if __name__=='__main__':main()
