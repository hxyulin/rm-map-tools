# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Verified rigid vector prototypes and quality-keyed tessellation reuse.

Rounded keys discover candidates only. A control-polynomial/formula bound must
admit each reuse; source identities, endpoints and placements remain separate.
"""
from dataclasses import dataclass
import hashlib,json,math
import numpy as np
from scipy.interpolate import PPoly
from cad_vector_ir import VectorCurve


def normalize(curve):
    """Return a proper rigid frame and derived local geometry; retain source data."""
    points=curve.evaluator().value(np.linspace(0,1,65));origin=points[0]
    x=points[-1]-origin
    if np.linalg.norm(x)<1e-9:x=points[np.argmax(np.linalg.norm(points-origin,axis=1))]-origin
    if np.linalg.norm(x)<1e-9:raise ValueError('degenerate vector prototype')
    x=x/np.linalg.norm(x);delta=points-origin;perpendicular=delta-(delta@x)[:,None]*x
    lengths=np.linalg.norm(perpendicular,axis=1)
    if lengths.max()>1e-8:
        y=perpendicular[np.flatnonzero(lengths>=lengths.max()*.5)[0]];y=y/np.linalg.norm(y)
    else:
        axis=np.eye(3)[np.argmin(abs(x))];y=axis-x*(axis@x);y=y/np.linalg.norm(y)
    rotation=np.column_stack((x,y,np.cross(x,y)))
    p=curve.parameters
    def positions(values):return ((np.array(values,dtype=float)-origin)@rotation).tolist()
    if curve.kind=='source-bspline':p['control_points']=positions(p['control_points'])
    else:
        p['endpoints_mm']=positions(p['endpoints_mm'])
        if curve.kind!='line':
            p['origin_mm']=positions([p['origin_mm']])[0]
            p['axes_rows']=(np.array(p['axes_rows'])@rotation).tolist()
            p['endpoint_corrections_mm']=(np.array(p['endpoint_corrections_mm'])@rotation).tolist()
    origin=origin.copy();origin.flags.writeable=False;rotation.flags.writeable=False
    return VectorCurve.make(curve.kind,p),origin,rotation


def difference_bound(a,b):
    """Bound corresponding complete vector curves, independently of sampled keys."""
    if a.kind!=b.kind:return math.inf
    if a.data==b.data:return 0.
    pa,pb=a.parameters,b.parameters
    if a.kind=='line':return float(np.linalg.norm(np.array(pa['endpoints_mm'])-pb['endpoints_mm'],axis=1).max())
    if a.kind=='source-bspline':
        ea,eb=a.evaluator(),b.evaluator();degree=max(ea.spline.k,eb.spline.k)
        polys=[]
        for e in (ea,eb):polys.append([PPoly.from_spline((e.spline.t,e.spline.c[:,axis],e.spline.k)) for axis in range(3)])
        breaks=np.unique(np.r_[ea.breaks,eb.breaks]);maximum=0.
        for lo,hi in zip(breaks,breaks[1:]):
            mid=(lo+hi)/2;bound=0.
            for order in range(degree+1):
                values=[]
                for e,pp in zip((ea,eb),polys):
                    values.append(np.array([poly(e.parameter_start+e.parameter_span*mid,nu=order) for poly in pp])*e.parameter_span**order)
                bound+=float(np.linalg.norm(values[0]-values[1]))*((hi-lo)/2)**order/math.factorial(order)
            maximum=max(maximum,bound)
        return maximum
    corrections=float(np.linalg.norm(np.array(pa['endpoint_corrections_mm'])-pb['endpoint_corrections_mm'],axis=1).max())
    if a.kind=='ellipse':
        aa=np.array(pa['axes_rows'])*np.array(pa['radii_mm'])[:,None];bb=np.array(pb['axes_rows'])*np.array(pb['radii_mm'])[:,None]
        phase=abs(pa['start_angle_rad']-pb['start_angle_rad'])+abs(pa['angle_span_rad']-pb['angle_span_rad'])
        return float(np.linalg.norm(np.array(pa['origin_mm'])-pb['origin_mm']))+float(np.linalg.norm(aa-bb,axis=1).sum())+float(np.linalg.norm(bb,axis=1).sum())*phase+corrections
    def coefficients(p):
        x,y=np.array(p['axes_rows']);a,b,c,d=p['coefficients'];length=p['length_mm']
        return np.array(p['origin_mm'])+a*y,length*(x+b*y),c*y,d*y,2*np.pi*length/p['period_mm']
    ca,cb=coefficients(pa),coefficients(pb)
    return sum(float(np.linalg.norm(x-y)) for x,y in zip(ca[:4],cb[:4]))+(np.linalg.norm(cb[2])+np.linalg.norm(cb[3]))*abs(ca[4]-cb[4])+corrections


@dataclass(frozen=True)
class PrototypeUse:
    """One independent curve use with its verified proper rigid placement."""
    prototype: int
    origin: object
    rotation: object
    original: VectorCurve
    deviation_bound_mm: float


class VectorCache:
    """In-memory verified prototype pool with exact quality-setting cache keys."""
    def __init__(self,normalization_error_mm=1e-6):
        if not math.isfinite(normalization_error_mm) or normalization_error_mm<=1e-8:raise ValueError('invalid normalization budget')
        self.epsilon=normalization_error_mm;self.prototypes=[];self.buckets={};self.meshes={};self.uses=0;self.hits=0;self.reuses=0

    def register(self,curve):
        local,origin,rotation=normalize(curve)
        def rounded(value):
            if isinstance(value,dict):return {k:rounded(v) for k,v in value.items()}
            if isinstance(value,list):return [rounded(v) for v in value]
            if isinstance(value,(float,int,str)) and not isinstance(value,bool):
                try:return round(float(value)/self.epsilon)
                except ValueError:return value
            return value
        key=hashlib.sha256((local.kind+json.dumps(rounded(local.parameters),sort_keys=True)).encode()).digest()
        selected=None;bound=0.
        for index in self.buckets.get(key,[]):
            bound=difference_bound(local,self.prototypes[index])+1e-8
            if bound<=self.epsilon:selected=index;self.reuses+=1;break
        if selected is None:
            selected=len(self.prototypes);self.prototypes.append(local);self.buckets.setdefault(key,[]).append(selected);bound=1e-8
        self.uses+=1
        return PrototypeUse(selected,origin,rotation,curve,bound)

    def sample(self,use,tolerance_mm):
        """Reuse one local mesh per prototype/tolerance, then pin original endpoints."""
        allowance=tolerance_mm-2*self.epsilon
        if allowance<=1e-10:raise ValueError('requested curve quality below normalization allowance')
        key=(use.prototype,float(allowance).hex())
        if key in self.meshes:self.hits+=1
        else:self.meshes[key]=self.prototypes[use.prototype].evaluator().tessellate(allowance)
        parameters,local,bound=self.meshes[key];points=local@use.rotation.T+use.origin
        points[[0,-1]]=use.original.evaluator().value([0,1])
        return parameters.copy(),points,{'curve_error_bound_mm':bound+2*self.epsilon,'prototype':use.prototype,
                                       'normalization_bound_mm':use.deviation_bound_mm,'chord_bound_mm':bound}

    def statistics(self):return {'uses':self.uses,'prototypes':len(self.prototypes),'verified_definition_reuses':self.reuses,
                                 'tessellation_entries':len(self.meshes),'tessellation_hits':self.hits,'normalization_allowance_mm':self.epsilon}
