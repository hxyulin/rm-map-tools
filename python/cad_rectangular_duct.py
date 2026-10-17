# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Explicit rectangular flange/duct proxies for reviewed source components."""
import math
import numpy as np


def flanged_duct(*, duct_length_mm, duct_width_mm, duct_height_mm, wall_mm,
                 flange_width_mm, flange_height_mm, flange_thickness_mm):
    """Build a through-open rectangular duct and its thick mounting-frame ring.

    The duct runs along +X, width along Y, height along Z, starting at X=0.
    The flange occupies X=duct_length..duct_length+flange_thickness. Its
    opening continues the duct's inner opening. No internal interface faces
    are generated. Returns shared positions in millimetres, outward-wound
    triangles and per-triangle part ids (0 flange, 1 duct). The complete union
    is a closed, two-manifold material shell surrounding a through passage;
    individual named parts have matching open interfaces.

    This is a caller-authorized approximation, not inferred CAD equivalence.
    Source fitting, placement, colour and collision policy remain caller-owned.
    """
    values=[duct_length_mm,duct_width_mm,duct_height_mm,wall_mm,
            flange_width_mm,flange_height_mm,flange_thickness_mm]
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in values):raise ValueError('duct dimensions must be finite positive millimetres')
    if 2*wall_mm>=min(duct_width_mm,duct_height_mm) or flange_width_mm<=duct_width_mm or flange_height_mm<=duct_height_mm:raise ValueError('invalid duct opening or flange margin')
    points=[];triangles=[];parts=[];cache={}
    def vertex(p):
        key=tuple(map(float,p))
        if key not in cache:cache[key]=len(points);points.append(key)
        return cache[key]
    def ring(x,width,height):
        return [vertex((x,y*width/2,z*height/2)) for y,z in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    def quad(ids,part,reverse=False):
        if reverse:ids=list(reversed(ids))
        triangles.extend([[ids[0],ids[1],ids[2]],[ids[0],ids[2],ids[3]]]);parts.extend([part,part])
    def cap(x,outer,inner,part,reverse):
        a=ring(x,*outer);b=ring(x,*inner)
        for i in range(4):j=(i+1)%4;quad([a[i],a[j],b[j],b[i]],part,reverse)
    def sides(x0,x1,size,part,reverse=False):
        a=ring(x0,*size);b=ring(x1,*size)
        for i in range(4):j=(i+1)%4;quad([a[i],a[j],b[j],b[i]],part,reverse)
    body=(duct_width_mm,duct_height_mm);opening=(duct_width_mm-2*wall_mm,duct_height_mm-2*wall_mm);flange=(flange_width_mm,flange_height_mm);end=duct_length_mm+flange_thickness_mm
    cap(end,flange,opening,0,False);cap(duct_length_mm,flange,body,0,True)
    sides(duct_length_mm,end,flange,0);sides(duct_length_mm,end,opening,0,True)
    sides(0,duct_length_mm,body,1);sides(0,duct_length_mm,opening,1,True);cap(0,body,opening,1,True)
    return np.array(points,float),np.array(triangles,np.int64),np.array(parts,np.uint8)
