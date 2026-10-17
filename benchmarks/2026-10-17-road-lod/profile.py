#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Plot actual source-road profile with selectable sections per physical wave.

Uniform-x preview is independent of the conservative knot-preserving component
mesher. Error is sampled against original spline evaluations, not certified.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'python'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from cad_vector_ir import VectorCurve
from plan_cad_lods import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    graph=json.loads((args.component/'component.json').read_text())
    if graph['component_id']!='red-road-surface/body-3789460':raise ValueError('unsupported measured profile selection')
    dense=[]
    for edge in ('3788941','3788943'):
        record=graph['edges'][edge]['geometry']
        evaluator=VectorCurve.make(record['kind'],record['parameters']).evaluator()
        points=evaluator.value(np.linspace(0,1,250001))
        dense.append(points)
    reference=np.concatenate(dense);reference=reference[np.argsort(reference[:,0])]
    # Plot in the local profile x/z plane; variation in y is below a micrometre.
    profile=reference[:,[0,2]];profile-=profile.min(axis=0)
    peaks,_=find_peaks(profile[:,1],prominence=20)
    waves=len(peaks)
    if waves!=10:raise ValueError('source wave count changed')
    mesh=np.load(args.component/'geometry.npz')
    current={str(face):int((mesh['source_face_ids']==face).sum())//2 for face in (3788952,3789250)}
    lods=[];candidates=[]
    for per_wave in (8,12,16,24,32):
        xs=np.linspace(0,profile[-1,0],per_wave*waves+1)
        points=np.column_stack((xs,np.interp(xs,profile[:,0],profile[:,1])))
        indices=np.clip(np.searchsorted(xs,profile[:,0],side='right')-1,0,len(xs)-2)
        a,b=points[indices],points[indices+1];v=b-a
        t=np.clip(np.sum((profile-a)*v,axis=1)/np.sum(v*v,axis=1),0,1)
        error=float(np.linalg.norm(profile-(a+t[:,None]*v),axis=1).max())
        lods.append({'sections_per_wave':per_wave,'waves':waves,'sections_total':per_wave*waves,
                     'top_surface_triangles_per_road':2*per_wave*waves,
                     'max_sampled_profile_distance_mm':error})
        candidates.append(points)
    args.out.mkdir(parents=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig=plt.figure(figsize=(12,10),layout='constrained');grid=fig.add_gridspec(4,2,height_ratios=[.9,1,1,1])
    overview=fig.add_subplot(grid[0,:]);overview.plot(profile[:,0],profile[:,1],color='#182331',lw=1)
    overview.set(title='Actual source road profile: 10 waves across 2.406 m',xlabel='Distance along road (mm)',ylabel='Height (mm)')
    overview.set_ylim(-5,80)
    # A whole wave, from first to second peak, avoids implying a guessed sine fit.
    left,right=profile[peaks[3],0],profile[peaks[4],0]
    mask=(profile[:,0]>=left)&(profile[:,0]<=right)
    colors=['#b74b45','#bd7a29','#1d75a1','#357b56','#7052a1']
    for index,(lod,points,color) in enumerate(zip(lods,candidates,colors)):
        ax=fig.add_subplot(grid[1+index//2,index%2])
        local=(points[:,0]>=left-40)&(points[:,0]<=right+40)
        ax.plot(profile[mask,0]-left,profile[mask,1],color='#182331',lw=2,label='Source spline')
        ax.plot(points[local,0]-left,points[local,1],'-o',color=color,lw=1.3,ms=4,label='LOD chords')
        ax.set_xlim(0,right-left);ax.set_ylim(-5,80)
        ax.set(title=f"{lod['sections_per_wave']} sections/wave: max sampled error {lod['max_sampled_profile_distance_mm']:.2f} mm",
               xlabel='Distance within one wave (mm)',ylabel='Height (mm)')
        ax.set_aspect('equal',adjustable='box');ax.grid(alpha=.2)
    legend=fig.add_subplot(grid[3,1]);legend.axis('off')
    legend.text(0,1,'Each section = one quad = 2 triangles\non one extruded surface.\n\nCurrent vector border prototype:\n987 top sections / 10 waves (~99/wave)\n1,346 underside sections (~135/wave)\n\nPreview LODs use uniform x spacing.\nErrors use 500,002 source samples.\nCaps, walls and shared seams are excluded.',va='top',linespacing=1.6)
    preview_x=np.linspace(left,right,1601)
    preview={'reference':np.column_stack((preview_x-left,np.interp(preview_x,profile[:,0],profile[:,1]))).tolist(),
             'wave_length_mm':float(right-left),'lods':[{'metrics':lod,'points':points[(points[:,0]>=left-40)&(points[:,0]<=right+40)].__sub__([left,0]).tolist()} for lod,points in zip(lods,candidates)]}
    (args.out/'profile-preview.json').write_text(json.dumps(preview,separators=(',',':'))+'\n')
    fig.savefig(args.out/'road-profile-lods.png',dpi=180)
    fig.savefig(args.out/'road-profile-lods.svg')
    plt.close(fig)
    report={'source_component_sha256':digest(args.component/'component.json'),'source_sha256':graph['parent_source_sha256'],
            'source_edges':[3788941,3788943],'profile_length_mm':float(profile[-1,0]),'waves':waves,
            'current_vector_profile_sections':current,'lods':lods,'reference_samples':len(profile),
            'scope':'2D x/z diagnostic of the source profile. Uniform-x preview does not replace native geometry, '
                    'the knot-preserving component mesher or whole-body/shared-seam collision validation.',
            'producer_sha256':digest(__file__)}
    (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
