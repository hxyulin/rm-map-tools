#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Matched native component previews with optional before/after wall candidates."""
import importlib.util,shutil,subprocess,tempfile,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('review',ROOT/'benchmarks/2026-10-17-terrain-separation/render-review.py')
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


def clip(triangles,low,high):
    """Clip diagnostic triangles to exact planes, independent of triangulation."""
    result=[]
    for triangle in triangles:
        polygon=list(triangle)
        for axis in range(3):
            for boundary,sign in ((low[axis],1),(high[axis],-1)):
                output=[]
                for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                    da=sign*(a[axis]-boundary);db=sign*(b[axis]-boundary)
                    if da>=0:output.append(a)
                    if (da<0)!=(db<0):output.append(a+(b-a)*(da/(da-db)))
                polygon=output
                if not polygon:break
            if not polygon:break
        for i in range(1,len(polygon)-1):result.append([polygon[0],polygon[i],polygon[i+1]])
    return np.asarray(result).reshape(-1,3,3)


def main():
    source=Path(sys.argv[1]);candidate=Path(sys.argv[2]) if len(sys.argv)>2 else None
    names=['under-highland-fan-grille','tunnel-fan-grille','central-tunnel-side','central-tunnel-side','central-tunnel-side-red','central-tunnel-side','central-tunnel-side-red'] if candidate else ['central-deck','central-tunnel-side','red-trapezoid-highland','under-highland-fan-grille','tunnel-fan-grille']
    yup=np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float)
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);cpp=ROOT/'benchmarks/2026-10-17-source-separation/scratch-source/cad-audit/non-base/depth-raster.cpp'
        (tmp/'raster.cpp').write_text(cpp.read_text().replace('im(w*h*3,245);','im(w*h*3,245);for(int k=0;k<w*h;k++){im[k*3]=192;im[k*3+1]=208;im[k*3+2]=224;}'))
        raster=tmp/'raster';subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(tmp/'raster.cpp'),'-o',str(raster)],check=True)
        canvas=Image.new('RGB',(1500,len(names)*440),'#f2f4f7');draw=ImageDraw.Draw(canvas)
        for row,name in enumerate(names):
            chunks=review.chunks(source/name/'source.glb',placement=yup)
            # Low angle reveals apertures under deck edges, not just top paint.
            view=((.8,.65,1.3) if row>=5 else ((.819,-.28,.573) if row in (2,4) else (-.819,-.28,-.573))) if candidate and 'grille' not in name else ((.8,.65,1.3) if 'grille' not in name else (.3,.7,1.5))
            variants=[('Source',chunks)]
            path=candidate/name/'candidate.glb' if candidate else None
            if path and path.exists():variants.append(('Filled wall',review.chunks(path,placement=yup)))
            else:variants.append(('Source reverse',chunks))
            prepared=[]
            for title,geometry in variants:
                if candidate and 'grille' not in name and row<5:
                    bounds=([1.8,-100,0.95],[3.5,100,3.35]) if name.endswith('-red') else ([-3.5,-100,-6.6],[-1.8,100,-4.2])
                    geometry=[(clip(p,*bounds),c) for p,c in geometry]
                    geometry=[(p,c) for p,c in geometry if len(p)]
                prepared.append((title,geometry))
            forward=np.array(view,float);forward/=np.linalg.norm(forward);right=np.cross([0,1,0],forward);right/=np.linalg.norm(right);up=np.cross(forward,right)
            all_points=np.concatenate([p for _,g in prepared for p,_ in g])@np.column_stack((right,up,forward))
            framing=(all_points.min((0,1)),all_points.max((0,1)))
            for col,(title,geometry) in enumerate(prepared):
                v=view if candidate or col==0 else tuple(-x if i!=1 else x for i,x in enumerate(view))
                panel=tmp/'panel.png';review.rasterize(geometry,panel,raster,tmp,view=v,width=735,height=390,framing=framing if candidate else None)
                x=10+col*750;y=40+row*440;canvas.paste(Image.open(panel),(x,y));draw.text((x,y-28),name+' / '+title,fill='#17202f',font_size=17)
        target=(candidate or source)/'review.png';canvas.save(target);print(target)
if __name__=='__main__':main()
