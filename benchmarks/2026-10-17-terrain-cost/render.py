#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Matched source-terrain diagnostic views; no geometry modification."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('review',ROOT/'benchmarks/2026-10-17-terrain-separation/render-review.py')
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('audit',type=Path);args=parser.parse_args()
    source=ROOT/'benchmarks/2026-10-17-source-separation/scratch-source/cad-audit/non-base/depth-raster.cpp'
    yup=np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],float)
    panels=[('Main dark road shell - wave region', 'red-road-surface/shell-3797315',True),
            ('Colored border solid - same wave region','red-road-surface/body-3789460',True),
            ('Floor slab and source markings','floor/body-23736',False),
            ('Highland and source markings','red-trapezoid-highland/body-2643575',False)]
    canvas=Image.new('RGB',(1200,900),'#f2f4f7');draw=ImageDraw.Draw(canvas)
    with tempfile.TemporaryDirectory() as folder:
        temporary=Path(folder);raster=temporary/'raster'
        cpp=source.read_text().replace('im(w*h*3,245);','im(w*h*3,245);for(int k=0;k<w*h;k++){im[k*3]=192;im[k*3+1]=208;im[k*3+2]=224;}')
        (temporary/'raster.cpp').write_text(cpp)
        subprocess.run([shutil.which('clang++') or shutil.which('g++'),'-O3',str(temporary/'raster.cpp'),'-o',str(raster)],check=True)
        for index,(title,cid,crop) in enumerate(panels):
            chunks=review.chunks(args.audit/cid/'visual.glb',placement=yup)
            if crop:
                selected=[]
                for triangles,color in chunks:
                    centers=triangles.mean(axis=1)
                    # Y-up coordinates: source x, source z, -source y, in metres.
                    mask=(centers[:,0]>6.30)&(centers[:,0]<8.78)&(centers[:,2]>-9.14)&(centers[:,2]<-7.00)
                    if mask.any():selected.append((triangles[mask],color))
                chunks=selected
            path=temporary/'panel.png'
            review.rasterize(chunks,path,raster,temporary,view=(.7,2.4,1.6),width=580,height=385)
            x=10+(index%2)*600;y=48+(index//2)*450
            canvas.paste(Image.open(path),(x,y));draw.text((x,y-30),title,fill='#17202f',font_size=19)
            if crop:draw.text((x,y+390),'Source wave region only; illustrative lighting',fill='#546174',font_size=14)
        canvas.save(args.audit/'terrain-review.png')


if __name__=='__main__':main()
