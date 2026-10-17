#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Standalone Base cost and centroid-density figures, keeping original geometry."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from triangle_density import centroid_grid


def main():
    out=Path(sys.argv[1]);audit=json.loads((out/'audit.json').read_text());analysis=json.loads((out/'analysis.json').read_text());data=np.load(out/'geometry.npz',allow_pickle=False);tri=data['positions_mm'][data['triangles']]/1000
    # Original Base local +Y is up; hierarchy rotations map it to field +Z.
    grids=[]
    for order in ((0,1,2),(0,2,1)):
        points=tri[:,:,order];lo=np.floor(points[:,:,:2].min((0,1))/.025)*.025;hi=np.ceil(points[:,:,:2].max((0,1))/.025)*.025
        grids.append((centroid_grid(points,lower_m=lo,upper_m=hi,cell_size_m=.025),lo,hi))
    fig,axes=plt.subplots(1,2,figsize=(12,6),constrained_layout=True);maximum=max(g[0].max() for g in grids);cmap=plt.get_cmap('inferno').copy();cmap.set_bad('#e9eef3')
    for ax,(grid,lo,hi),title,ylabel in zip(axes,grids,['Front projection','Top projection'],['Local height +Y (m)','Local Z (m)']):
        image=ax.imshow(np.ma.masked_equal(grid,0),origin='lower',extent=[lo[0],hi[0],lo[1],hi[1]],norm=LogNorm(vmin=1,vmax=maximum),cmap=cmap,interpolation='nearest');ax.set_title(title);ax.set_xlabel('Local X (m)');ax.set_ylabel(ylabel);ax.set_aspect('equal')
        assert int(grid.sum())==audit['definition_triangles']
    fig.colorbar(image,ax=axes,label='Triangle centroids / 25 × 25 mm cell (log scale)',shrink=.8);fig.suptitle('Original Base · all 709,354 triangles · source pose')
    fig.savefig(out/'density.png',dpi=170);fig.savefig(out/'density.svg');plt.close(fig)
    ids=[(4527988,'Lower outer housing'),(4268930,'Top crossbar'),(4392221,'Tall cover A'),(4314593,'Tall cover B'),(4353403,'Tall cover C'),(4756187,'Small module back shell'),(4594338,'Module frame')]
    lookup={u['source_id']:u for u in analysis['units']};labels=[f'{name} · #{source}' for source,name in ids];seen=[lookup[i]['observed_in_external_views'] for i,_ in ids];unseen=[lookup[i]['not_observed_in_external_views'] for i,_ in ids]
    fig,ax=plt.subplots(figsize=(11,5),constrained_layout=True);ax.barh(labels,seen,label='Observed by sampled exterior views',color='#4385b7');ax.barh(labels,unseen,left=seen,label='Not observed in those views',color='#bbc5d2');ax.invert_yaxis();ax.set_xlabel('Triangles per source unit');ax.legend(loc='lower right');ax.set_title('Native Base costs · descriptive labels from inspection, not motion bindings')
    for y,(a,b) in enumerate(zip(seen,unseen)):ax.text(a+b+1000,y,f'{a+b:,}',va='center',fontsize=9)
    ax.set_xlim(0,190000);fig.savefig(out/'costs.png',dpi=170);fig.savefig(out/'costs.svg');plt.close(fig)
if __name__=='__main__':main()
