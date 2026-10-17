#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Report saturated light-color pixel masks in matched complete-equipment renders."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image


def masks(path):
    p=np.asarray(Image.open(path).convert('RGB')).astype(float);r,g,b=p.transpose(2,0,1)
    return {'red':(r>3*g)&(r>3*b)&(r>40),'green':(g>3*r)&(g>3*b)&(g>40),'blue':(b>3*r)&(b>3*g)&(b>40)}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();review=json.loads((a.out/'review.json').read_bytes());results=[]
    for row in review['entries']:
        if row['scope']!='complete' or row['id']=='complete-field':continue
        for view in row['view_names']:
            folder=a.out/row['images'];before=masks(folder/('reference-'+view+'.png'));after=masks(folder/('candidate-'+view+'.png'))
            results.append({'group':row['id'],'view':view,'colors':{key:{'before_pixels':int(before[key].sum()),'after_pixels':int(after[key].sum()),'changed_pixels':int((before[key]!=after[key]).sum())} for key in before}})
    (a.out/'color-masks.json').write_text(json.dumps({'views':results,'scope':'Saturated RGB diagnostic pixel masks in flat source-color renders, not semantic detector/artwork masks. Exact source geometry/material retention is checked separately.'},indent=2)+'\n')
    print('Maximum saturated-color mask changes',{key:max(r['colors'][key]['changed_pixels'] for r in results) for key in ['red','green','blue']})
if __name__=='__main__':main()
