"""Matched source / closed-envelope Outpost previews, including context."""
import importlib.util,json,subprocess,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('render_outpost_closed',Path(__file__).with_name('render.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def main():
    proof=json.loads((m.OUT/'outpost-export-verification.json').read_text());_,_,before=m.original.load_nodes(proof['source']);_,_,after=m.original.load_nodes(proof['candidate'])
    subjects=[];views=[]
    with tempfile.TemporaryDirectory()as td:
        tmp=Path(td);helper=ROOT/'out/rmuc2027-conservative-shape-audit/raster'
        if not helper.is_file():
            helper=tmp/'raster';subprocess.run(['clang++','-O3','-std=c++17',str(ROOT/'benchmarks/2026-10-17-base-panel-textures/texture-raster.cpp'),'-o',str(helper)],check=True)
        for scope in ['one-block','all-three-context']:
            ids=[26]if scope=='one-block'else[26,28,30]
            selected=np.concatenate([before[i]for i in ids]);trial=np.concatenate([after[i]for i in ids])
            rest=np.concatenate([g for ni,g in before.items()if ni not in ids])
            if scope=='one-block':
                b=m.colored(selected,np.arange(len(selected)));a=m.colored(trial,np.arange(len(trial)),(.18,.65,.85))
            else:
                b=m.colored(np.concatenate([rest,selected]),np.arange(len(rest),len(rest)+len(selected)))
                a=m.colored(np.concatenate([rest,trial]),np.arange(len(rest),len(rest)+len(trial)),(.18,.65,.85))
            for direction,label in [((1,.65,1),'oblique'),((-1,.65,-1),'reverse')]:
                for stage,data in [('source',b),('proxy',a)]:
                    path=m.OUT/f'outpost-{scope}-{label}-{stage}.webp'
                    Image.fromarray(m.r.raster(data,m.old.data(selected,[.6,.6,.6])[0],direction,helper,tmp)).save(path,lossless=True)
                    views.append(dict(scope=scope,view=label,stage=stage,path=str(path),sha256=m.original.digest(path)))
    (m.OUT/'outpost-renders.json').write_text(json.dumps(views,indent=2)+'\n')


if __name__=='__main__':main()
