#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Plot source samples and fitted primitives from the retained audit evidence."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def plot(report,destination):
    curves={c['source_edge_id']:c for c in report['curve_examples']}
    road=curves[3795912];ellipse=curves[1430864]
    figure,axes=plt.subplots(1,2,figsize=(10,3.6),gridspec_kw={'width_ratios':[1.7,1]},layout='constrained')
    model=next(m for m in road['models'] if m['model']=='sinusoid')
    frame=model['frame_source_units'];points=np.array(road['profile_samples_mm'])
    local=(points-np.array(frame['origin']))@np.array(frame['basis_rows']).T
    p=model['parameters'];xx=np.linspace(local[:,0].min(),local[:,0].max(),3000)
    a,b,c,d=p['coefficients_offset_slope_sin_cos'];yy=a+b*xx+c*np.sin(2*np.pi*xx/p['period'])+d*np.cos(2*np.pi*xx/p['period'])
    axes[0].plot(xx,yy,color='#168ab7',label='Sine fit',lw=1.5)
    axes[0].plot(local[:,0],local[:,1],'.',color='#263343',markersize=3,label='Source samples')
    axes[0].set(title='Road profile · source edge #3795912',xlabel='Distance along profile (mm)',ylabel='Profile height (mm)')
    axes[0].text(.02,.03,f"Period {p['period']:.6f} mm\nMax sampled error {model['max_sample_error_source_units']:.6f} mm",transform=axes[0].transAxes,fontsize=9,bbox={'facecolor':'white','alpha':.85,'edgecolor':'none'})
    axes[0].legend(loc='upper right',fontsize=8);axes[0].set_ylim(-8,88)
    model=next(m for m in ellipse['models'] if m['model']=='ellipse');p=model['parameters']
    frame=model['plane_frame_source_units'];points=np.array(ellipse['profile_samples_mm'])
    local=(points-np.array(frame['origin']))@np.array(frame['basis_rows']).T
    t=np.linspace(0,2*np.pi,1000);r=p['radii'];angle=p['angle_rad']
    rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    fitted=np.column_stack((r[0]*np.cos(t),r[1]*np.sin(t)))@rotation.T+np.array(p['center_uv'])
    axes[1].plot(fitted[:,0],fitted[:,1],color='#168ab7',lw=1.5,label='Complete ellipse')
    axes[1].plot(local[:,0],local[:,1],'.',color='#263343',markersize=3,label='Source edge samples')
    axes[1].set(title='Tech Core · edge #1430864',xlabel='Local plane u (mm)',ylabel='Local plane v (mm)',aspect='equal')
    axes[1].legend(fontsize=8);axes[1].text(.02,.03,f"Max sampled error\n{model['max_sample_error_source_units']:.6f} mm",transform=axes[1].transAxes,fontsize=9,bbox={'facecolor':'white','alpha':.85,'edgecolor':'none'})
    for ax in axes:
        ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)
    destination.parent.mkdir(parents=True,exist_ok=True)
    figure.savefig(destination,dpi=180);plt.close(figure)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=Path(__file__).with_name('summary.json'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();plot(json.loads(args.report.read_text()),args.out)
