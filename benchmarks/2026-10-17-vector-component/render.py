#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Render same-camera source and vector component comparisons from local output."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from cad_component import NativeComponent


def render(directory,output):
    report=json.loads((directory/'summary.json').read_text());graph=json.loads((directory/'component.json').read_text());data=np.load(directory/'geometry.npz')
    with NativeComponent(directory/'source.step',graph['source_body_id']) as component:
        bp,bt,bf,_=component.mesh(report['native_mesh_baseline']['linear_deflection_mm'],report['native_mesh_baseline']['angular_deflection_rad'])
    optimized=(data['positions_mm'],data['triangles'],data['source_face_ids']);source=(bp,bt,bf)
    curved=[face['source_face_id'] for face in graph['faces'] if graph['surfaces'][str(face['source_surface_id'])]['kind']=='SURFACE_OF_LINEAR_EXTRUSION']
    detail=optimized[0][optimized[1][np.isin(optimized[2],curved)]].reshape(-1,3)
    image=Image.new('RGB',(1200,720),'#f4f5f7');draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=19)
    labels=[f'Source native · {len(bt):,} triangles',f'Vector component · {len(optimized[1]):,} triangles']
    for row in range(2):
        for column,(points,triangles,faces) in enumerate((source,optimized)):
            left=column*600;top=row*360
            draw.text((left+16,top+12),labels[column],fill='#182431',font=font)
            draw.text((left+16,top+40),'Complete source body · XY view' if row==0 else 'Wave region · XZ view, vertical scale x6',fill='#526372',font=ImageFont.load_default(size=15))
            region=Image.new('RGB',(568,272),'white');rd=ImageDraw.Draw(region)
            axes=[0,1] if row==0 else [0,2];stretch=np.array([1.,1. if row==0 else 6.]);reference=points if row==0 else detail
            projected=reference[:,axes]*stretch;lo=projected.min(0);hi=projected.max(0);extent=hi-lo;scale=min(530/max(extent[0],1),226/max(extent[1],1));center=(lo+hi)/2
            q=(points[:,axes]*stretch-center)*[scale,-scale]+[284,136]
            depth=points[:,2] if row==0 else points[:,1];order=np.argsort(depth[triangles].mean(1))
            colours=report['source_face_colours']
            for index in order:
                t=triangles[index];xy=q[t]
                if xy[:,0].max()<0 or xy[:,0].min()>568 or xy[:,1].max()<0 or xy[:,1].min()>272:continue
                colour=colours[str(int(faces[index]))]
                rgb=np.array(list(map(float,colour.split(',')))) if colour else np.array([.6,.6,.6])
                normal=np.cross(points[t[1]]-points[t[0]],points[t[2]]-points[t[0]]);length=np.linalg.norm(normal)
                light=.5+.5*abs(float(normal@np.array([.25,.45,.86]))/length) if length>1e-15 else .5
                rd.polygon([tuple(p) for p in xy],fill=tuple(np.clip(rgb*light*255,0,255).astype(int)))
            image.paste(region,(left+16,top+70))
    output.parent.mkdir(parents=True,exist_ok=True);image.save(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();render(args.directory,args.out)
