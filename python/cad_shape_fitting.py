# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measured primitive-fit proposals; never mutate or certify source geometry.

Polygon corner bounds cover corresponding straight segments. Curve errors are
sampled Euclidean distances/residuals, not continuous Hausdorff certificates.
"""
import math
import re

import numpy as np
from scipy.interpolate import BSpline
from scipy.optimize import least_squares, minimize_scalar
from cad_optimizer import TOKEN
from cad_ir_structure import PassContract
from cad_patch_matching import exact_point, scalar_args


def plane_coordinates(points):
    points=np.asarray(points,dtype=float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<3 or not np.isfinite(points).all():
        raise ValueError('expected at least three finite 3D points')
    center=points.mean(axis=0);_,s,vt=np.linalg.svd(points-center,full_matrices=False)
    if s[0]<=1e-12:raise ValueError('coincident samples')
    return center,vt,(points-center)@vt.T


def rectangle_fit(points):
    """Fit ordered four corners to an orthogonal rectangle, retaining all errors."""
    points=np.asarray(points,dtype=float)
    if points.shape!=(4,3):raise ValueError('rectangle requires four ordered corners')
    center,basis,local=plane_coordinates(points)
    signs=np.array([[-1,-1],[1,-1],[1,1],[-1,1]])
    u=signs[:,0]@local[:,:2]/4;v=signs[:,1]@local[:,:2]/4
    jv=np.array([v[1],-v[0]])
    _,eigen=np.linalg.eigh(np.outer(u,u)+np.outer(jv,jv));x=eigen[:,-1];y=np.array([-x[1],x[0]])
    a=float(u@x);b=float(v@y)
    fitted=center+(signs[:,0,None]*a*x+signs[:,1,None]*b*y)@basis[:2]
    if min(abs(a),abs(b))<1e-9:raise ValueError('degenerate rectangle')
    error=np.linalg.norm(points-fitted,axis=1)
    return {'model':'rectangle','half_extents_source_units':[abs(a),abs(b)],
            'corners':fitted.tolist(),'max_corner_error_source_units':float(error.max()),
            'rms_corner_error_source_units':float(np.sqrt(np.mean(error**2))),
            'error_scope':'original vertex-polyline corresponding segments; not a healed/native B-rep deviation certificate'}


def simplify_polygon(points, tolerance):
    """Remove near-collinear corners and bound original-to-chord displacement.

    The final bound is rechecked against all original chain vertices and monotone
    chord projections. This covers both directions for these straight chains.
    """
    points=np.asarray(points,dtype=float);n=len(points)
    if n<3 or tolerance<0 or not np.isfinite(points).all():raise ValueError('invalid polygon')
    keep=list(range(n))
    def error(a,b,indices):
        delta=points[b]-points[a];length=float(delta@delta)
        if length<=1e-18:return math.inf
        t=(points[indices]-points[a])@delta/length
        if np.any(np.diff(t)<-1e-10) or t.min()<-1e-10 or t.max()>1+1e-10:return math.inf
        return float(np.linalg.norm(points[indices]-(points[a]+t[:,None]*delta),axis=1).max())
    changed=True
    while changed and len(keep)>3:
        changed=False
        for i in range(len(keep)):
            a,b=keep[i-1],keep[(i+1)%len(keep)]
            chain=[(a+j)%n for j in range((b-a)%n+1)]
            if error(a,b,chain)<=tolerance:
                keep.pop(i);changed=True;break
    bounds=[]
    for a,b in zip(keep,keep[1:]+keep[:1]):
        chain=[(a+j)%n for j in range((b-a)%n+1)]
        bounds.append(error(a,b,chain))
    return points[keep],{'corner_indices':keep,'original_corners':n,'retained_corners':len(keep),
                         'continuous_chain_error_bound_source_units':max(bounds)}


def polygon_fits(points, tolerance=.1):
    """Find near triangles/rectangles and measure right-angle departures."""
    corners,reduction=simplify_polygon(points,tolerance)
    result={'simplification':reduction,'models':[]}
    directions=np.roll(corners,-1,axis=0)-corners
    lengths=np.linalg.norm(directions,axis=1)
    if np.any(lengths<=1e-12):return result
    angles=np.degrees(np.arccos(np.clip(np.sum(-np.roll(directions,1,axis=0)*directions,axis=1)/(np.roll(lengths,1)*lengths),-1,1)))
    result['corner_angles_degrees']=angles.tolist()
    if len(corners)==4:
        proposal=rectangle_fit(corners)
        proposal['continuous_boundary_error_bound_source_units']=proposal['max_corner_error_source_units']+reduction['continuous_chain_error_bound_source_units']
        result['models'].append(proposal)
    if len(corners)==3:
        result['models'].append({'model':'triangle','corners':corners.tolist(),
            'continuous_boundary_error_bound_source_units':reduction['continuous_chain_error_bound_source_units'],
            'nearest_right_angle_error_degrees':float(np.min(abs(angles-90)))})
        # Keep one corner fixed; choose orthogonal leg axes and project both legs.
        for index in range(3):
            origin=corners[index];a=corners[(index+1)%3]-origin;b=corners[(index+2)%3]-origin
            _,basis,local=plane_coordinates(corners)
            a=a@basis[:2].T;b=b@basis[:2].T;jb=np.array([b[1],-b[0]])
            _,eigen=np.linalg.eigh(np.outer(a,a)+np.outer(jb,jb));x=eigen[:,-1];y=np.array([-x[1],x[0]])
            proposed=corners.copy();proposed[(index+1)%3]=origin+(a@x)*x@basis[:2];proposed[(index+2)%3]=origin+(b@y)*y@basis[:2]
            maximum=float(np.linalg.norm(proposed-corners,axis=1).max())
            result['models'].append({'model':'right_triangle','right_corner_index':index,'corners':proposed.tolist(),
                'continuous_boundary_error_bound_source_units':maximum+reduction['continuous_chain_error_bound_source_units']})
    return result


def _curve_frame(points):
    center,basis,local=plane_coordinates(points)
    return center,basis,local[:,:2],float(np.max(abs(local[:,2])))


def fit_round_profiles(training, validation):
    """Fit lines/circles/ellipses on training samples; measure held-out distances."""
    center,basis,xy,plane_error=_curve_frame(training)
    validation=np.asarray(validation);uv=(validation-center)@basis.T
    results=[]
    def report(model,errors,parameters):
        results.append({'model':model,'parameters':parameters,'sample_count':len(validation),
                        'max_sample_error_source_units':float(np.max(errors)),
                        'rms_sample_error_source_units':float(np.sqrt(np.mean(np.asarray(errors)**2))),
                        'plane_frame_source_units':{'origin':center.tolist(),'basis_rows':basis.tolist()},
                        'error_scope':'held-out sampled distance; not a continuous deviation certificate'})
    report('line',np.linalg.norm(uv[:,1:],axis=1),{})
    if np.linalg.svd(xy-xy.mean(axis=0),compute_uv=False)[1]<1e-8:return results
    circle=least_squares(lambda p:np.linalg.norm(xy-p[:2],axis=1)-p[2],
                         [0,0,max(np.std(xy,axis=0))],bounds=([-np.inf,-np.inf,1e-10],[np.inf]*3),max_nfev=150)
    report('circle',np.hypot(np.linalg.norm(uv[:,:2]-circle.x[:2],axis=1)-circle.x[2],uv[:,2]),
           {'center_uv':circle.x[:2].tolist(),'radius':float(circle.x[2])})
    # Direct conic initialization (u^2, uv, v^2, u, v, 1), then radial LS.
    scale=max(float(np.ptp(xy,axis=0).max()),1e-8);q=xy/scale
    _,_,vt=np.linalg.svd(np.column_stack((q[:,0]**2,q[:,0]*q[:,1],q[:,1]**2,q[:,0],q[:,1],np.ones(len(q)))),full_matrices=False)
    aa,bb,cc,dd,ee,ff=vt[-1];matrix=np.array([[aa,bb/2],[bb/2,cc]])
    try:
        mid=-np.linalg.solve(matrix,[dd,ee])/2
        eigen,axes=np.linalg.eigh(matrix);radius_squared=-(ff+np.dot([dd,ee],mid)+mid@matrix@mid)/eigen
        if np.any(radius_squared<=0):return results
        radii=np.sqrt(radius_squared)*scale;mid=mid*scale;angle=math.atan2(axes[1,0],axes[0,0])
    except np.linalg.LinAlgError:return results
    def transformed(p,coords):
        delta=coords-p[:2];c,s=np.cos(p[4]),np.sin(p[4])
        return np.column_stack((delta[:,0]*c+delta[:,1]*s,-delta[:,0]*s+delta[:,1]*c))
    def residual(p):
        transformed_xy=transformed(p,xy);r=np.exp(p[2:4]);t=np.arctan2(transformed_xy[:,1]/r[1],transformed_xy[:,0]/r[0])
        return np.linalg.norm(transformed_xy-np.column_stack((r[0]*np.cos(t),r[1]*np.sin(t))),axis=1)
    initial=[*mid,*np.log(radii),angle]
    fit=least_squares(residual,initial,max_nfev=150)
    radii=np.exp(fit.x[2:4])
    if not np.isfinite(radii).all() or np.max(radii)>scale*1e5:return results
    local=transformed(fit.x,uv[:,:2]);distances=[]
    # Global closest-point search on the complete ellipse, refined locally.
    grid=np.linspace(-np.pi,np.pi,129)
    outline=np.column_stack((radii[0]*np.cos(grid),radii[1]*np.sin(grid)))
    for point,z in zip(local,uv[:,2]):
        guess=grid[np.argmin(np.sum((outline-point)**2,axis=1))]
        objective=lambda t:float(np.sum((np.array([radii[0]*np.cos(t),radii[1]*np.sin(t)])-point)**2))
        minimum=minimize_scalar(objective,bounds=(guess-np.pi/64,guess+np.pi/64),method='bounded',options={'xatol':1e-12})
        distances.append(math.sqrt(max(0,minimum.fun)+z*z))
    report('ellipse',distances,{'center_uv':fit.x[:2].tolist(),'radii':radii.tolist(),'angle_rad':float(fit.x[4])})
    return results


def fit_wave_profiles(training, validation):
    """Compare sine waves and repeated semielliptic arches in a monotone plane.

    Axes come from the end-to-end chord and best-fit plane. Arches with height
    equal to half-period are semicircles; unequal axes are semiellipses.
    """
    training=np.asarray(training,dtype=float);validation=np.asarray(validation,dtype=float)
    center,basis,local=plane_coordinates(training)
    x=training[-1]-training[0];x/=np.linalg.norm(x)
    normal=basis[2];y=np.cross(normal,x);y/=np.linalg.norm(y)
    axes=np.array([x,y,normal]);q=(training-training[0])@axes.T;v=(validation-training[0])@axes.T
    if np.any(np.diff(q[:,0])<-1e-7) or np.any(np.diff(v[:,0])<-1e-7):return []
    span=float(q[-1,0]);
    if span<=1e-8:return []
    # At least 1.5 periods guards against calling an isolated arc a wave.
    lo,hi=1.5/span, min(12/span,(len(training)-1)/(8*span))
    if hi<=lo:return []
    def solve(frequency,phase=0,arch=False):
        xx=q[:,0];phase_x=xx*frequency+phase
        if arch:
            shape=np.sqrt(np.maximum(0,1-(2*(phase_x%1)-1)**2))
            design=np.column_stack((np.ones(len(xx)),xx,shape))
        else:design=np.column_stack((np.ones(len(xx)),xx,np.sin(2*np.pi*phase_x),np.cos(2*np.pi*phase_x)))
        coefficients=np.linalg.lstsq(design,q[:,1],rcond=None)[0]
        return float(np.mean((design@coefficients-q[:,1])**2)),coefficients
    grid=np.linspace(lo,hi,80);best=int(np.argmin([solve(f)[0] for f in grid]))
    frequency=minimize_scalar(lambda f:solve(f)[0],bounds=(grid[max(0,best-1)],grid[min(len(grid)-1,best+1)]),method='bounded',options={'xatol':1e-13}).x
    _,coefficients=solve(frequency)
    predicted=coefficients[0]+coefficients[1]*v[:,0]+coefficients[2]*np.sin(2*np.pi*frequency*v[:,0])+coefficients[3]*np.cos(2*np.pi*frequency*v[:,0])
    def report(model,predicted,parameters):
        error=np.hypot(predicted-v[:,1],v[:,2])
        return {'model':model,'parameters':parameters,'sample_count':len(validation),
                'max_sample_error_source_units':float(np.max(error)),
                'rms_sample_error_source_units':float(np.sqrt(np.mean(error**2))),
                'frame_source_units':{'origin':training[0].tolist(),'basis_rows':axes.tolist()},
                'error_scope':'held-out same-abscissa displacement; not continuous deviation certificate'}
    results=[report('sinusoid',predicted,{'period':1/frequency,'coefficients_offset_slope_sin_cos':coefficients.tolist()})]
    candidates=sorted((solve(f,p,True)[0],f,p) for f in grid for p in np.linspace(0,1,12,endpoint=False))[:4]
    def arch_residual(values):
        f,p=values;_,c=solve(f,p,True);shape=np.sqrt(np.maximum(0,1-(2*((q[:,0]*f+p)%1)-1)**2))
        return c[0]+c[1]*q[:,0]+c[2]*shape-q[:,1]
    optimized=[least_squares(arch_residual,[f,p],bounds=([lo,-1],[hi,2]),max_nfev=100) for _,f,p in candidates]
    fit=min(optimized,key=lambda item:np.sum(item.fun**2));frequency,phase=fit.x;_,c=solve(frequency,phase,True)
    shape=np.sqrt(np.maximum(0,1-(2*((v[:,0]*frequency+phase)%1)-1)**2))
    results.append(report('semiellipse_train',c[0]+c[1]*v[:,0]+c[2]*shape,
                          {'period':1/frequency,'phase_turns':float(phase),'offset_slope_height':c.tolist(),
                           'height_to_half_period_ratio':float(abs(c[2])*2*frequency)}))
    return results


def split_arguments(text):
    """Split one simple STEP entity's top-level arguments without losing nesting."""
    text=text.strip();start=text.index(b'(')+1;end=text.rfind(b')');parts=[];depth=0;previous=start
    literals={m.start():m.end() for m in TOKEN.finditer(text) if m.group().startswith((b"'",b'"',b'/*'))}
    i=start
    while i<end:
        if i in literals:i=literals[i];continue
        token=text[i:i+1]
        if token==b'(':depth+=1
        elif token==b')':depth-=1
        elif token==b',' and depth==0:parts.append(text[previous:i].strip());previous=i+1
        i+=1
    parts.append(text[previous:end].strip());return parts


def bspline_samples(document, edge_id, count):
    """Evaluate a simple nonrational full-span B-spline source edge in order.

    Complex/rational forms and partial trims are rejected; no OCCT ordinal is
    treated as a source ID. Endpoint agreement is checked, not assumed.
    """
    ix=document.index;row=ix.r(edge_id);refs=list(map(int,ix.refs_of(row)))
    if ix.tname(row)!='EDGE_CURVE' or len(refs)!=3:raise ValueError('not an edge curve')
    curve=ix.r(refs[2])
    if ix.tname(curve)!='B_SPLINE_CURVE_WITH_KNOTS':raise ValueError('not a simple B-spline curve')
    args=split_arguments(ix.text(curve).split(b'=',1)[1]);degree=int(args[1])
    if len(args)!=9:raise ValueError('unsupported B-spline arguments')
    controls=[int(v) for v in re.findall(rb'#(\d+)',args[2])]
    coordinates=np.array([exact_point(ix,point) for point in controls],dtype=float)
    multiplicities=[int(v) for v in re.findall(rb'\d+',args[6])]
    knots=[float(v) for v in re.findall(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?',args[7])]
    if len(knots)!=len(multiplicities):raise ValueError('invalid spline knot arrays')
    expanded=np.repeat(knots,multiplicities)
    if len(expanded)!=len(coordinates)+degree+1 or np.any(np.diff(expanded)<0):raise ValueError('invalid spline dimensions')
    spline=BSpline(expanded,coordinates,degree,extrapolate=False)
    parameters=np.linspace(expanded[degree],expanded[-degree-1],count)
    samples=spline(parameters)
    ends=[]
    for vertex in refs[:2]:
        point=ix.refs_of(ix.r(vertex))
        if ix.tname(ix.r(vertex))!='VERTEX_POINT' or len(point)!=1:raise ValueError('unsupported spline vertex')
        ends.append(np.array(exact_point(ix,int(point[0])),dtype=float))
    direct=max(np.linalg.norm(samples[0]-ends[0]),np.linalg.norm(samples[-1]-ends[1]))
    reverse=max(np.linalg.norm(samples[-1]-ends[0]),np.linalg.norm(samples[0]-ends[1]))
    if min(direct,reverse)>1e-6:raise ValueError('partial spline trim / endpoint mismatch')
    return samples if direct<=reverse else samples[::-1]


def native_spline_sample_error(document,edge_id,samples):
    """Cross-check source-derived SciPy samples against independent OCCT evaluation.

    This checks evaluation, not a fitted replacement's continuous deviation.
    No full-model transfer, healing, mesh or source ordinal inference is involved.
    """
    from OCP.collections import Array1_gp_Pnt,Array1_double,Array1_int
    from OCP.Geom import Geom_BSplineCurve
    from OCP.gp import gp_Pnt
    ix=document.index;curve=int(ix.refs_of(ix.r(edge_id))[2])
    args=split_arguments(ix.text(ix.r(curve)).split(b'=',1)[1]);degree=int(args[1])
    controls=[int(v) for v in re.findall(rb'#(\d+)',args[2])]
    points=Array1_gp_Pnt(1,len(controls))
    for i,source in enumerate(controls,1):points.SetValue(i,gp_Pnt(*map(float,exact_point(ix,source))))
    multiplicities=[int(v) for v in re.findall(rb'\d+',args[6])]
    knots=[float(v) for v in re.findall(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?',args[7])]
    native_knots=Array1_double(1,len(knots));native_multiplicities=Array1_int(1,len(knots))
    for i,(k,m) in enumerate(zip(knots,multiplicities),1):
        native_knots.SetValue(i,k);native_multiplicities.SetValue(i,m)
    curve=Geom_BSplineCurve(points,native_knots,native_multiplicities,degree,False)
    values=np.array([curve.Value(float(t)).Coord() for t in np.linspace(curve.FirstParameter(),curve.LastParameter(),len(samples))])
    error=min(float(np.linalg.norm(values-samples,axis=1).max()),float(np.linalg.norm(values[::-1]-samples,axis=1).max()))
    if error>1e-7:raise ValueError('SciPy/native source evaluation mismatch')
    return error


FIT_CONTRACT = PassContract('primitive-fit-proposals-v1',
    ('finite ordered polygon vertices or sampled full-span simple B-spline','explicit source units','held-out curve samples'),
    ('source CAD','source use identity and metadata','all runtime assets'),
    'source face/edge ID, owner components, source-local bounds, fitted parameters and explicit error scope',
    'vertex-polyline displacement bounds or held-out sampled errors; no continuous curve certificate or automatic edit')
