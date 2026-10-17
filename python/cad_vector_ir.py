# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Resolution-independent finite vector curves and conservative automatic fits.

Portable selections retain exact source decimal spline data and independently
identified uses. Evaluators use float64; arbitrary resolution is not arbitrary
numeric precision. Tight exports fall back to the original parametric source.
"""
from dataclasses import dataclass,asdict
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
from scipy.interpolate import BSpline,PPoly
from cad_patch_matching import exact_point,sense
from cad_shape_fitting import split_arguments


@dataclass(frozen=True)
class FitPolicy:
    """Automatic length-error budget, in millimetres, with a feature-size cap."""
    max_error_mm: float = .25
    feature_fraction: float = .005
    certificate_slack_mm: float = .005
    numeric_guard_mm: float = 1e-8
    max_intervals: int = 65536

    def __post_init__(self):
        if any(not math.isfinite(v) or v<=0 for v in (self.max_error_mm,self.feature_fraction,self.certificate_slack_mm,self.numeric_guard_mm)):
            raise ValueError('policy values must be positive and finite')
        if not 0<self.feature_fraction<1 or self.max_intervals<64:raise ValueError('invalid fit policy')

    def budget(self,feature_mm):
        if not math.isfinite(feature_mm) or feature_mm<=0:raise ValueError('invalid feature size')
        return min(self.max_error_mm,self.feature_fraction*feature_mm)


@dataclass(frozen=True)
class VectorCurve:
    """Immutable formula/control data on normalized domain [0,1], never a mesh."""
    kind: str
    data: bytes  # canonical JSON; source decimal parameters remain strings

    @classmethod
    def make(cls,kind,data):
        if kind not in ('source-bspline','line','ellipse','sinusoid'):raise ValueError('unsupported vector primitive')
        return cls(kind,json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode())

    @property
    def parameters(self):return json.loads(self.data)

    @property
    def key(self):return hashlib.sha256(b'rm-vector-curve-v1\0'+self.kind.encode()+b'\0'+self.data).hexdigest()

    def evaluator(self):return CurveEvaluator(self)


class CurveEvaluator:
    """Float64 evaluator with conservative piecewise second-derivative bounds."""
    def __init__(self,curve):
        self.kind=curve.kind;self.p=curve.parameters;self.spline=None
        if self.kind=='source-bspline':
            p=self.p;knots=np.repeat(np.array(p['knots'],dtype=float),p['multiplicities']);degree=p['degree']
            coordinates=np.array(p['control_points'],dtype=float)
            lo,hi=knots[degree],knots[-degree-1]
            if hi<=lo or len(knots)!=len(coordinates)+degree+1:raise ValueError('invalid vector spline domain')
            normalized=(knots-lo)/(hi-lo)
            self.spline=BSpline(normalized,coordinates,degree,extrapolate=False)
            breaks=np.unique(normalized[(normalized>=0)&(normalized<=1)])
            start,end=p.get('trim_parameters',[0.,1.])
            if p['reverse']:start,end=end,start
            if not 0<=min(start,end)<max(start,end)<=1:raise ValueError('invalid source spline trim')
            self.parameter_start=float(start);self.parameter_span=float(end-start)
            local=(breaks-start)/(end-start)
            self.breaks=np.unique(np.r_[0.,local[(local>0)&(local<1)],1.])
            # Power coefficients bound each polynomial span, even when repeated
            # knots prevent the global BSpline.derivative(2) API from working.
            pp=[PPoly.from_spline((normalized,coordinates[:,axis],degree)) for axis in range(3)]
            coefficients=np.stack([poly.c for poly in pp],axis=-1)
            widths=np.diff(pp[0].x);bounds=np.zeros(len(widths))
            for row,power in enumerate(range(degree,-1,-1)):
                if power>=2:bounds+=np.linalg.norm(coefficients[row],axis=1)*power*(power-1)*widths**(power-2)
            self.pp_breaks=pp[0].x;self.span_bounds=bounds
        else:
            self.breaks=np.array([0.,1.])
            if self.kind=='line':self.bound=0.
            elif self.kind=='ellipse':self.bound=float(np.linalg.norm(np.array(self.p['axes_rows']).T@np.diag(self.p['radii_mm']),ord=2))*self.p['angle_span_rad']**2
            elif self.kind=='sinusoid':
                a,b,c,d=self.p['coefficients'];self.bound=math.hypot(c,d)*float(np.linalg.norm(self.p['axes_rows'][1]))*(2*math.pi*self.p['length_mm']/self.p['period_mm'])**2
            else:raise ValueError('unknown vector curve')
        probes=self.value(np.array([0.,.5,1.]))
        if not np.isfinite(probes).all():raise ValueError('nonfinite vector curve')

    def value(self,t):
        t=np.atleast_1d(np.asarray(t,dtype=float))
        if not np.isfinite(t).all() or np.any(t<0) or np.any(t>1):raise ValueError('curve parameter outside [0,1]')
        p=self.p
        if self.spline is not None:return self.spline(self.parameter_start+self.parameter_span*t)
        if self.kind=='line':
            value=np.array(p['endpoints_mm'][0])+t[:,None]*(np.array(p['endpoints_mm'][1])-p['endpoints_mm'][0])
            value[t==0]=p['endpoints_mm'][0];value[t==1]=p['endpoints_mm'][1]
            return value
        if self.kind=='ellipse':
            angle=p['start_angle_rad']+t*p['angle_span_rad'];r=p['radii_mm']
            local=np.column_stack((r[0]*np.cos(angle),r[1]*np.sin(angle)))
            value=np.array(p['origin_mm'])+local@np.array(p['axes_rows'])
        else:
            x=t*p['length_mm'];a,b,c,d=p['coefficients'];angle=2*np.pi*x/p['period_mm']
            y=a+b*x+c*np.sin(angle)+d*np.cos(angle)
            value=np.array(p['origin_mm'])+np.column_stack((x,y))@np.array(p['axes_rows'])
        correction=np.array(p['endpoint_corrections_mm']);value+=(1-t[:,None])*correction[0]+t[:,None]*correction[1]
        # All original uses of a shared endpoint export exactly the same numeric
        # vertex, rather than depending on cancellation in a fitted formula.
        value[t==0]=p['endpoints_mm'][0];value[t==1]=p['endpoints_mm'][1]
        return value

    def second_bound(self,a,b):
        if self.spline is None:return self.bound
        middle=self.parameter_start+self.parameter_span*(a+b)/2
        pos=int(np.searchsorted(self.pp_breaks,middle,side='right')-1)
        return float(self.span_bounds[min(max(pos,0),len(self.span_bounds)-1)])*self.parameter_span**2

    def tessellate(self,tolerance_mm,*,max_segments=262144):
        """Return parameters/points and a chord-error bound, or fail at the cap.

        Knot spans partition source splines first. A second-derivative bound
        controls every chord, so flat midpoint coincidences cannot hide waves.
        """
        if not math.isfinite(tolerance_mm) or tolerance_mm<=1e-10:raise ValueError('export tolerance must exceed float64 numeric floor (1e-10 mm)')
        parameters=list(map(float,self.breaks));maximum=0.
        if len(parameters)-1>max_segments:raise ValueError('source knot partition exceeds tessellation segment limit')
        while True:
            split=[];maximum=0.
            for a,b in zip(parameters,parameters[1:]):
                bound=self.second_bound(a,b)*(b-a)**2/8
                maximum=max(maximum,bound)
                if bound>tolerance_mm:split.append((a+b)/2)
            if not split:break
            if len(parameters)+len(split)-1>max_segments:raise ValueError('vector tessellation segment limit reached')
            parameters=sorted(parameters+split)
        values=self.value(parameters)
        # Numeric noise is accounted separately from the analytic chord bound.
        return np.array(parameters),values,maximum


def source_spline(document,edge_id):
    """Extract a self-contained full-span nonrational source spline with lexemes."""
    ix=document.index;row=ix.r(edge_id);refs=list(map(int,ix.refs_of(row)))
    if ix.tname(row)!='EDGE_CURVE' or len(refs)!=3:raise ValueError('expected source edge curve')
    curve=ix.r(refs[2])
    if ix.tname(curve)!='B_SPLINE_CURVE_WITH_KNOTS':raise ValueError('unsupported source curve')
    args=split_arguments(ix.text(curve).split(b'=',1)[1])
    if len(args)!=9:raise ValueError('unsupported spline syntax')
    degree=int(args[1]);controls=[int(v) for v in re.findall(rb'#(\d+)',args[2])]
    points=[]
    from cad_patch_matching import scalar_args
    for source in controls:
        point=ix.r(source)
        if ix.tname(point)!='CARTESIAN_POINT':raise ValueError('unsupported control point')
        numbers=scalar_args(ix,point)
        if len(numbers)!=3:raise ValueError('expected 3D spline control')
        points.append([value.decode('ascii') for value in numbers])
    numbers=rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?'
    knots=[value.decode('ascii') for value in re.findall(numbers,args[7])]
    multiplicities=[int(value) for value in re.findall(rb'\d+',args[6])]
    if len(knots)!=len(multiplicities) or any(m<=0 for m in multiplicities):raise ValueError('invalid knot multiplicities')
    if any(m>degree for m in multiplicities[1:-1]):raise ValueError('discontinuous source spline')
    data={'degree':degree,'control_points':points,'knots':knots,'multiplicities':multiplicities,'reverse':False}
    geometry=VectorCurve.make('source-bspline',data);evaluation=geometry.evaluator()
    endpoints=[]
    for vertex in refs[:2]:
        row=ix.r(vertex);point=ix.refs_of(row)
        if ix.tname(row)!='VERTEX_POINT' or len(point)!=1:raise ValueError('unsupported source vertex')
        endpoints.append(list(map(float,exact_point(ix,int(point[0])))))
    samples=evaluation.value([0,1]);direct=max(np.linalg.norm(samples-np.array(endpoints),axis=1));reverse=max(np.linalg.norm(samples[::-1]-np.array(endpoints),axis=1))
    if min(direct,reverse)>1e-6:raise ValueError('partial source spline / endpoint mismatch')
    data['reverse']=bool(reverse<direct)
    return VectorCurve.make('source-bspline',data),tuple(refs[:2]),tuple(tuple(v) for v in endpoints),refs[2]


def fitted_curve(source,model,endpoints):
    """Construct finite, endpoint-pinned analytic geometry and a source pairing."""
    original=source.evaluator();training=original.value(np.linspace(0,1,129));kind=model['model'];p=model['parameters']
    if kind=='line':
        # A finite segment through the source endpoints, not an infinite TLS line.
        start,end=np.array(endpoints);delta=end-start;length=float(np.linalg.norm(delta))
        if length<=1e-8:raise ValueError('closed/degenerate line fit')
        geometry=VectorCurve.make('line',{'endpoints_mm':endpoints})
        mapping=lambda points:(points-start)@delta/(length*length)
        feature=length
    elif kind in ('circle','ellipse'):
        frame=model['plane_frame_source_units'];origin=np.array(frame['origin']);basis=np.array(frame['basis_rows'])[:2]
        center=np.array(p['center_uv']);origin=origin+center@basis
        radii=p['radii'] if kind=='ellipse' else [p['radius']]*2
        angle=p.get('angle_rad',0.);c,s=math.cos(angle),math.sin(angle)
        axes=np.array([[c,s],[-s,c]])@basis
        def phases(points):
            local=(points-origin)@axes.T
            return np.unwrap(np.arctan2(local[:,1]/radii[1],local[:,0]/radii[0]))
        angles=phases(training);start=float(angles[0]);span=float(angles[-1]-angles[0])
        if abs(span)<1e-8 or abs(span)>2*np.pi+1e-5:raise ValueError('unsupported finite arc winding')
        def mapping(points):
            values=phases(points)
            values+=2*np.pi*round((start-values[0])/(2*np.pi))
            return (values-start)/span
        data={'origin_mm':origin.tolist(),'axes_rows':axes.tolist(),'radii_mm':radii,
              'start_angle_rad':start,'angle_span_rad':span,'endpoints_mm':endpoints,'endpoint_corrections_mm':[[0.]*3]*2}
        # Evaluate the unpinned formula at its ends to compute correction.
        angles=np.array([start,start+span]);raw=origin+np.column_stack((radii[0]*np.cos(angles),radii[1]*np.sin(angles)))@axes
        data['endpoint_corrections_mm']=(np.array(endpoints)-raw).tolist()
        geometry=VectorCurve.make('ellipse',data);feature=2*min(radii)
    elif kind=='sinusoid':
        frame=model['frame_source_units'];origin=np.array(frame['origin']);axes=np.array(frame['basis_rows'])[:2]
        length=float((training[-1]-origin)@axes[0])
        if length<=1e-8 or p['period']<=0:raise ValueError('invalid sine domain')
        coefficients=p['coefficients_offset_slope_sin_cos']
        data={'origin_mm':origin.tolist(),'axes_rows':axes.tolist(),'length_mm':length,'period_mm':p['period'],
              'coefficients':coefficients,'endpoints_mm':endpoints,'endpoint_corrections_mm':[[0.]*3]*2}
        a,b,c,d=coefficients;x=np.array([0.,length]);theta=2*np.pi*x/p['period'];y=a+b*x+c*np.sin(theta)+d*np.cos(theta)
        raw=origin+np.column_stack((x,y))@axes
        data['endpoint_corrections_mm']=(np.array(endpoints)-raw).tolist()
        geometry=VectorCurve.make('sinusoid',data);mapping=lambda points:(points-origin)@axes[0]/length
        feature=min(p['period'],2*math.hypot(c,d))
    else:raise ValueError('no automatic vector conversion for this model')
    return geometry,mapping,feature


def certify_fit(source,candidate,mapping,policy,feature_mm):
    """Bound bidirectional curve displacement via corresponding chord intervals.

    Each source knot span and candidate parameter interval has a conservative
    second-derivative chord bound. Endpoint residual plus both chord bounds
    bounds both continuous curves, rather than just the sampled points.
    Floating arithmetic uses an explicit numeric guard; this is not formal
    interval arithmetic. Resource exhaustion rejects the fit.
    """
    original=source.evaluator();fitted=candidate.evaluator();budget=policy.budget(feature_mm)
    parameters=np.unique(np.r_[original.breaks,np.linspace(0,1,65)])
    if len(parameters)-1>policy.max_intervals:
        return {'accepted':False,'reason':'source knot partition exceeds interval limit','budget_mm':budget}
    refinements=0;target=budget
    while True:
        points=original.value(parameters);mapped=np.asarray(mapping(points),dtype=float)
        if not np.isfinite(mapped).all() or mapped.min()<-1e-7 or mapped.max()>1+1e-7 or np.any(np.diff(mapped)<-1e-7):
            return {'accepted':False,'reason':'nonmonotone or out-of-domain finite trim pairing','budget_mm':budget}
        mapped=np.clip(mapped,0,1);mapped[0]=0;mapped[-1]=1
        error=np.linalg.norm(points-fitted.value(mapped),axis=1)
        maximum=float(error.max())
        if maximum+policy.numeric_guard_mm>budget:
            return {'accepted':False,'reason':'paired curve residual exceeds policy','budget_mm':budget,'max_paired_residual_mm':maximum}
        if refinements==0:target=min(budget,maximum+max(policy.certificate_slack_mm,maximum*.05))
        # A denser pass may discover a higher peak; grow the tightening target
        # within the actual policy budget rather than mislabeling it as failure.
        target=min(budget,max(target,maximum+max(policy.certificate_slack_mm,maximum*.05)))
        bounds=[]
        for i,(a,b) in enumerate(zip(parameters,parameters[1:])):
            bound=max(error[i],error[i+1])+original.second_bound(a,b)*(b-a)**2/8+fitted.second_bound(mapped[i],mapped[i+1])*(mapped[i+1]-mapped[i])**2/8+policy.numeric_guard_mm
            bounds.append(float(bound))
        split=np.flatnonzero(np.array(bounds)>target)
        if not len(split):
            return {'accepted':True,'budget_mm':budget,'feature_mm':feature_mm,
                    'continuous_error_bound_mm':max(bounds),'max_paired_residual_mm':maximum,
                    'intervals':len(bounds),'refinements':refinements,'numeric_guard_mm':policy.numeric_guard_mm,
                    'method':'source-knot-span and analytic second-derivative chord bounds; pinned shared endpoints'}
        if len(parameters)+len(split)-1>policy.max_intervals:
            return {'accepted':False,'reason':'continuous certification interval limit','budget_mm':budget,'intervals':len(parameters)-1}
        parameters=np.sort(np.r_[parameters,(parameters[split]+parameters[split+1])/2]);refinements+=1


@dataclass(frozen=True)
class VectorUse:
    """Original source identity and topology stay independent of vector sharing."""
    source_edge_id: int
    source_curve_id: int
    vertex_ids: tuple
    endpoint_positions_mm: tuple
    same_sense: bool
    geometry: int
    fallback: int
    components: tuple
    decision: bytes


@dataclass(frozen=True)
class VectorPolygon:
    """Finite polygon boundary template with source corners and original fallback.

    Bounds refer to the original vertex polyline, not a healed native face. The
    owning source still supplies surface, materials, neighbors and solid topology.
    No independent right-angle snap moves a shared source corner.
    """
    source_face_id: int
    source_bound_id: int
    source_loop_id: int
    source_surface_id: int
    vertex_ids: tuple
    edge_ids: tuple
    oriented_edge_ids: tuple
    orientations: tuple
    original_points_mm: tuple
    corner_indices: tuple
    recognized_model: str
    decision: bytes

    def outline(self,tolerance_mm):
        proof=json.loads(self.decision)
        if not math.isfinite(tolerance_mm) or tolerance_mm<=proof['numeric_guard_mm']:raise ValueError('invalid outline tolerance or below numeric guard')
        points=np.array(self.original_points_mm,dtype=float)
        fallback=not proof['accepted'] or proof['boundary_error_bound_mm']>tolerance_mm
        return points if fallback else points[list(self.corner_indices)],{
            'source_face_id':self.source_face_id,'closed':True,'original_boundary_fallback':fallback,
            'boundary_error_bound_mm':proof['numeric_guard_mm'] if fallback else proof['boundary_error_bound_mm'],
            'scope':'original vertex-polyline boundary; native trimmed surface remains source-backed'}


def polygon_record(polygon):
    """Encode an integrity-checked portable polygon boundary definition."""
    record={**asdict(polygon),'decision':json.loads(polygon.decision)}
    return {**record,'sha256':hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()}


def vector_polygon(document,face_id,policy):
    """Automatically reduce collinear runs while pinning surviving source corners."""
    from cad_patch_matching import polygon_patch,scalar_args
    from cad_shape_fitting import polygon_fits
    patch=polygon_patch(document,face_id);points=patch.coordinates()
    _,_,basis=np.linalg.svd(points-points.mean(axis=0),full_matrices=False)
    normal=basis[-1];edges=np.roll(points,-1,axis=0)-points
    lengths=np.linalg.norm(edges,axis=1)
    if np.any(lengths<1e-12):raise ValueError('degenerate polygon boundary')
    directions=np.cross(normal,edges/lengths[:,None]);widths=np.ptp(points@directions.T,axis=0)
    feature=float(widths.min());budget=policy.budget(feature)
    fits=polygon_fits(points,tolerance=budget/2)
    indices=tuple(fits['simplification']['corner_indices']);source_corners=points[list(indices)]
    selected=None
    # Orthogonal/triangle recognition never independently moves shared corners.
    for model in fits['models']:
        if float(np.linalg.norm(source_corners-np.array(model['corners']),axis=1).max())<=policy.numeric_guard_mm:
            selected=model;break
    bound=fits['simplification']['continuous_chain_error_bound_source_units']+policy.numeric_guard_mm
    accepted=selected is not None and bound<=budget
    decision={'accepted':accepted,'budget_mm':budget,'feature_mm':feature,'boundary_error_bound_mm':bound,'numeric_guard_mm':policy.numeric_guard_mm,
              'source_corner_positions_pinned':True,'native_surface_replacement':False,
              'reason':'source-anchored polygon template' if accepted else 'retain original boundary; shared-corner or error constraint',
              'scope':'continuous original vertex-polyline boundary; not native surface/solid equivalence'}
    original=[]
    for vertex in patch.vertex_ids:
        point=int(document.index.refs_of(document.index.r(vertex))[0])
        original.append(tuple(v.decode() for v in scalar_args(document.index,document.index.r(point))))
    return VectorPolygon(face_id,patch.bound_id,patch.loop_id,patch.surface_id,patch.vertex_ids,patch.edge_ids,
                         patch.oriented_edge_ids,patch.orientations,tuple(original),indices,
                         selected['model'] if selected else 'source-polygon',json.dumps(decision,sort_keys=True).encode())


@dataclass(frozen=True)
class VectorIR:
    """Portable vector curves and source-anchored polygon boundary templates.

    Source faces, appearance, motion and assembly remain in the owning optimizer
    IR; this selection never claims to encode a complete field or closed solid.
    """
    source_sha256: str
    policy: FitPolicy
    geometries: tuple
    uses: tuple
    polygons: tuple = ()

    def export_curve(self,edge_id,total_error_mm):
        """Tessellate within a total source-relative error, with automatic fallback."""
        use=next((use for use in self.uses if use.source_edge_id==edge_id),None)
        if use is None:raise ValueError('edge outside vector selection')
        if not math.isfinite(total_error_mm) or total_error_mm<=2*self.policy.numeric_guard_mm:
            raise ValueError('requested export tolerance is below the numeric guard')
        decision=json.loads(use.decision)
        original=self.geometries[use.fallback].evaluator()
        pins=np.array(use.endpoint_positions_mm)
        endpoint_error=float(np.linalg.norm(original.value([0,1])-pins,axis=1).max())
        fitted_bound=decision.get('continuous_error_bound_mm',0.)
        selected=use.geometry;bound=fitted_bound if selected!=use.fallback else endpoint_error
        if bound+self.policy.numeric_guard_mm>=total_error_mm:
            selected=use.fallback;bound=endpoint_error
        if bound+self.policy.numeric_guard_mm>=total_error_mm:
            raise ValueError('shared source endpoint discrepancy exceeds requested export tolerance')
        parameters,points,chord=self.geometries[selected].evaluator().tessellate(total_error_mm-bound-self.policy.numeric_guard_mm)
        points[0]=pins[0];points[-1]=pins[1]
        return points,{'source_edge_id':edge_id,'geometry':selected,'source_fallback':selected==use.fallback,
                       'requested_total_error_mm':total_error_mm,'fit_or_endpoint_error_bound_mm':bound,
                       'tessellation_error_bound_mm':chord,'numeric_guard_mm':self.policy.numeric_guard_mm,
                       'total_error_bound_mm':bound+chord+self.policy.numeric_guard_mm,
                       'segments':len(parameters)-1}

    def write(self,path):
        """Write a fresh self-contained vector selection, including source controls and loops."""
        data={'software_license':'MIT OR Apache-2.0 (schema and tooling only)',
              'geometry_notice':'Source and derived geometry remain under source CAD ownership and terms; no new geometry license is granted. For DJI RoboMaster inputs see NOTICE.md.',
              'schema':'rm-cad-vector-selection-v1','source_sha256':self.source_sha256,'units':'mm',
              'coverage':'selected finite curves and polygon boundary templates; source CAD remains authority for native faces, solids and metadata',
              'policy':asdict(self.policy),'geometries':[{'kind':g.kind,'parameters':g.parameters,'sha256':g.key} for g in self.geometries],
              'uses':[{**asdict(u),'decision':json.loads(u.decision)} for u in self.uses],
              'polygon_boundaries':[polygon_record(p) for p in self.polygons]}
        data['content_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        with Path(path).open('x') as stream:json.dump(data,stream,indent=2,allow_nan=False);stream.write('\n')

    @classmethod
    def read(cls,path):
        """Reload a portable selection without STEP or the original CadDocument."""
        data=json.loads(Path(path).read_text())
        checksum=data.pop('content_sha256',None)
        if checksum!=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest():raise ValueError('vector selection content checksum mismatch')
        if re.fullmatch(r'[0-9a-f]{64}',data.get('source_sha256','')) is None:raise ValueError('invalid vector source checksum')
        if data.get('schema')!='rm-cad-vector-selection-v1' or data.get('units')!='mm':raise ValueError('unsupported vector schema/units')
        geometries=[]
        for entry in data['geometries']:
            geometry=VectorCurve.make(entry['kind'],entry['parameters'])
            if geometry.key!=entry['sha256']:raise ValueError('vector definition checksum mismatch')
            geometry.evaluator();geometries.append(geometry)
        uses=[];seen=set();vertices={}
        for entry in data['uses']:
            if entry['source_edge_id'] in seen:raise ValueError('duplicate vector use')
            seen.add(entry['source_edge_id'])
            positions=np.array(entry['endpoint_positions_mm'],dtype=float)
            if len(entry['vertex_ids'])!=2 or positions.shape!=(2,3) or not np.isfinite(positions).all() or not isinstance(entry['same_sense'],bool):
                raise ValueError('invalid vector topology/endpoint data')
            for vertex,point in zip(entry['vertex_ids'],positions):
                if vertex in vertices and not np.array_equal(vertices[vertex],point):raise ValueError('inconsistent shared source vertex')
                vertices[vertex]=point
            if any(not 0<=entry[key]<len(geometries) for key in ('geometry','fallback')):raise ValueError('invalid vector geometry reference')
            if geometries[entry['fallback']].kind!='source-bspline':raise ValueError('missing source spline fallback')
            if float(np.linalg.norm(geometries[entry['fallback']].evaluator().value([0,1])-positions,axis=1).max())>1e-6:
                raise ValueError('source spline/vertex endpoint disagreement')
            if entry['geometry']!=entry['fallback']:
                if not np.array_equal(geometries[entry['geometry']].evaluator().value([0,1]),positions):
                    raise ValueError('fitted geometry lost shared endpoint pins')
                decision=entry['decision']
                if not decision.get('accepted') or not math.isfinite(decision.get('continuous_error_bound_mm',math.nan)) or decision['continuous_error_bound_mm']<0:
                    raise ValueError('missing accepted fit evidence')
            uses.append(VectorUse(entry['source_edge_id'],entry['source_curve_id'],tuple(entry['vertex_ids']),tuple(tuple(v) for v in entry['endpoint_positions_mm']),entry['same_sense'],
                                  entry['geometry'],entry['fallback'],tuple(entry['components']),json.dumps(entry['decision'],sort_keys=True).encode()))
        polygons=[];seen_faces=set()
        for entry in data.get('polygon_boundaries',[]):
            checksum=entry.pop('sha256',None)
            if checksum!=hashlib.sha256(json.dumps(entry,sort_keys=True,separators=(',',':')).encode()).hexdigest():raise ValueError('polygon definition checksum mismatch')
            if entry['source_face_id'] in seen_faces:raise ValueError('duplicate polygon source face')
            seen_faces.add(entry['source_face_id'])
            for key in ('vertex_ids','edge_ids','oriented_edge_ids','orientations','corner_indices'):
                entry[key]=tuple(entry[key])
            entry['original_points_mm']=tuple(tuple(v) for v in entry['original_points_mm'])
            points=np.array(entry['original_points_mm'],dtype=float);n=len(points)
            if points.shape!=(n,3) or n<3 or not np.isfinite(points).all():raise ValueError('invalid polygon boundary')
            if any(len(entry[key])!=n for key in ('vertex_ids','edge_ids','oriented_edge_ids')) or len(entry['orientations'])!=2+2*n:
                raise ValueError('polygon boundary correspondence mismatch')
            if len(entry['corner_indices'])<3 or any(not 0<=i<n for i in entry['corner_indices']):raise ValueError('invalid polygon corner references')
            proof=entry['decision']
            if not math.isfinite(proof['boundary_error_bound_mm']) or proof['boundary_error_bound_mm']<0:raise ValueError('invalid polygon error evidence')
            entry['decision']=json.dumps(proof,sort_keys=True).encode();polygons.append(VectorPolygon(**entry))
        return cls(data['source_sha256'],FitPolicy(**data['policy']),tuple(geometries),tuple(uses),tuple(polygons))


def build_vector_ir(document,findings,*,policy=None):
    """Automatically accept the simplest certified primitive, retaining fallback.

    Findings must be checksum-pinned to this source. Rejected/unsupported models
    retain the original parametric spline. Source-anchored polygon templates
    reduce collinear boundary runs; native surface/solid edits remain separate.
    """
    document.require_open();document.verify_source();policy=policy or FitPolicy()
    if set(document.geometry_length_units)!={'.MILLI.,.METRE.'}:raise ValueError('vector policy requires millimetre geometry')
    if findings.get('source_sha256')!=document.source_sha256:raise ValueError('fit findings/input source mismatch')
    geometries=[];definitions={};uses=[];seen=set()
    def intern(geometry):
        key=(geometry.kind,geometry.data)
        if key not in definitions:definitions[key]=len(geometries);geometries.append(geometry)
        return definitions[key]
    complexity={'line':0,'circle':1,'ellipse':2,'sinusoid':3}
    for entry in findings['curve_examples']:
        edge=entry['source_edge_id']
        if edge in seen:raise ValueError('duplicate source edge findings')
        seen.add(edge);original,vertices,endpoints,curve=source_spline(document,edge);fallback=intern(original)
        selected=fallback;decisions=[];accepted=None
        for model in sorted((m for m in entry['models'] if m['model'] in complexity),key=lambda m:complexity[m['model']]):
            try:
                candidate,mapping,feature=fitted_curve(original,model,endpoints)
                decision=certify_fit(original,candidate,mapping,policy,feature)
            except (ValueError,np.linalg.LinAlgError) as error:decision={'accepted':False,'reason':str(error)}
            decisions.append({'model':model['model'],**decision})
            if decision['accepted']:
                selected=intern(candidate);accepted={'model':model['model'],**decision};break
        decision=accepted or {'accepted':False,'reason':'no primitive met the automatic policy; retain source spline'}
        decision={**decision,'trials':decisions}
        uses.append(VectorUse(edge,curve,vertices,endpoints,sense(document.index,edge),selected,fallback,tuple(entry['components']),json.dumps(decision,sort_keys=True,allow_nan=False).encode()))
    polygons=[];faces=set()
    for example in findings.get('polygon_examples_first_40',[]):
        face=example['source_face_id']
        if face not in faces:
            polygons.append(vector_polygon(document,face,policy));faces.add(face)
    document.verify_source()
    return VectorIR(document.source_sha256,policy,tuple(geometries),tuple(uses),tuple(polygons))


@dataclass(frozen=True)
class RuledSurface:
    """Parametric ruled patch between two finite vector curves, in millimetres.

    This defines a surface; boundary agreement alone never certifies that an
    original CAD face has this interior. Source-face binding is a later pass.
    """
    first: VectorCurve
    second: VectorCurve
    reverse_second: bool = False

    def value(self,u,v):
        """Evaluate corresponding normalized u positions and transverse v blends."""
        u,v=np.broadcast_arrays(np.atleast_1d(u),np.atleast_1d(v))
        if not np.isfinite(v).all() or np.any(v<0) or np.any(v>1):raise ValueError('surface parameter outside [0,1]')
        a=self.first.evaluator().value(u.ravel());b=self.second.evaluator().value((1-u if self.reverse_second else u).ravel())
        return ((1-v.ravel()[:,None])*a+v.ravel()[:,None]*b).reshape(*u.shape,3)

    def tessellate(self,tolerance_mm,*,max_segments=262144):
        """Triangulate within a surface chord bound, including bilinear twist.

        Unlike curves, two triangles through four noncoplanar strip corners
        also need a mixed-derivative/twist term; dropping it misses saddle error.
        The bound is relative to this mathematical patch, not an unverified CAD
        interior. Source fitting error is a separate budget.
        """
        if not math.isfinite(tolerance_mm) or tolerance_mm<=1e-10:raise ValueError('invalid surface tolerance')
        first=self.first.evaluator();second=self.second.evaluator()
        breaks=1-second.breaks[::-1] if self.reverse_second else second.breaks
        parameters=np.unique(np.r_[first.breaks,breaks])
        if len(parameters)-1>max_segments:raise ValueError('surface knot partition exceeds tessellation segment limit')
        while True:
            a=first.value(parameters);b=second.value(1-parameters if self.reverse_second else parameters)
            bounds=[]
            for i,(lo,hi) in enumerate(zip(parameters,parameters[1:])):
                second_lo,second_hi=(1-hi,1-lo) if self.reverse_second else (lo,hi)
                chord=max(first.second_bound(lo,hi),second.second_bound(second_lo,second_hi))*(hi-lo)**2/8
                twist=float(np.linalg.norm((b[i+1]-b[i])-(a[i+1]-a[i])))/4
                bounds.append(chord+twist)
            split=np.flatnonzero(np.array(bounds)>tolerance_mm)
            if not len(split):break
            if len(parameters)+len(split)-1>max_segments:raise ValueError('surface tessellation segment limit reached')
            parameters=np.sort(np.r_[parameters,(parameters[split]+parameters[split+1])/2])
        vertices=np.stack((a,b),axis=1).reshape(-1,3)
        triangles=np.array([(2*i,2*i+2,2*i+1) for i in range(len(parameters)-1)]+
                           [(2*i+1,2*i+2,2*i+3) for i in range(len(parameters)-1)],dtype=np.uint32)
        return vertices,triangles,{'segments':len(parameters)-1,'triangles':len(triangles),'surface_error_bound_mm':max(bounds),
                                   'scope':'defined ruled patch only; source interior and fit errors are separate'}


from cad_ir_structure import PassContract

VECTOR_CONTRACT = PassContract('automatic-vector-selection-v1',
    ('checksum-pinned findings and millimetre source','simple full-span source splines','finite straight-boundary polygon subset'),
    ('source IDs and topology uses','shared endpoint positions','original spline decimal parameters','original CAD and runtime assets'),
    'source edge to accepted finite formula plus exact-parametric fallback; source face to pinned-corner boundary template',
    'continuous curve/chord budget with numeric guard; polygon bound is vertex-polyline only; selected coverage, not whole-field mesh savings')
