# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Source-defined component surfaces, verified native binding and shared meshes.

Native meshing consumes the retained source B-rep. Approximate vector curve
fits never independently replace the boundaries of a source surface here.
"""
from collections import Counter,defaultdict
import json
from pathlib import Path

import numpy as np
from cad_patch_matching import exact_point,scalar_args,sense
from cad_shape_fitting import split_arguments
from cad_vector_ir import VectorCurve,source_spline


def refs(ix,source):return tuple(map(int,ix.refs_of(ix.r(source))))


def source_bspline_curve(document,curve):
    """Expand an untrimmed spline construction with original decimal parameters."""
    import re
    ix=document.index
    if ix.tname(ix.r(curve))!='B_SPLINE_CURVE_WITH_KNOTS':raise ValueError('unsupported extrusion basis')
    args=split_arguments(ix.text(ix.r(curve)).split(b'=',1)[1])
    controls=[int(v) for v in re.findall(rb'#(\d+)',args[2])]
    data={'degree':int(args[1]),'control_points':[[v.decode() for v in scalar_args(ix,ix.r(source))] for source in controls],
          'knots':[v.decode() for v in re.findall(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?',args[7])],
          'multiplicities':list(map(int,re.findall(rb'\d+',args[6]))),'reverse':False}
    return VectorCurve.make('source-bspline',data)


def component_spline(document,edge):
    """Retain a source spline construction and explicitly project its finite trim.

    Partial trims are recorded rather than silently promoted to full curves.
    The native edge remains the authority for component meshing.
    """
    try:return source_spline(document,edge)
    except ValueError as error:
        if 'endpoint mismatch' not in str(error):raise
    import re
    from scipy.optimize import minimize_scalar
    ix=document.index;start,end,curve=refs(ix,edge);args=split_arguments(ix.text(ix.r(curve)).split(b'=',1)[1])
    controls=[int(v) for v in re.findall(rb'#(\d+)',args[2])]
    data={'degree':int(args[1]),'control_points':[[v.decode() for v in scalar_args(ix,ix.r(source))] for source in controls],
          'knots':[v.decode() for v in re.findall(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?',args[7])],
          'multiplicities':list(map(int,re.findall(rb'\d+',args[6]))),'reverse':False}
    base=VectorCurve.make('source-bspline',data).evaluator();parameters=[];positions=[]
    for vertex in (start,end):
        point=np.array(exact_point(ix,refs(ix,vertex)[0]),dtype=float);positions.append(tuple(point))
        candidates=[(float(np.linalg.norm(base.value([t])[0]-point)),float(t)) for t in base.breaks]
        for a,b in zip(base.breaks,base.breaks[1:]):
            fit=minimize_scalar(lambda t:float(np.sum((base.value([t])[0]-point)**2)),bounds=(a,b),method='bounded',options={'xatol':1e-15})
            candidates.append((float(np.sqrt(fit.fun)),float(fit.x)))
        distance,parameter=min(candidates)
        if distance>.001:raise ValueError('source spline trim endpoint outside source tolerance')
        parameters.append(parameter)
    data['trim_parameters']=parameters
    return VectorCurve.make('source-bspline',data),(start,end),tuple(positions),curve


def component_graph(document,body_id):
    """Capture a closed solid's complete face/loop/edge incidence and surfaces."""
    ix=document.index;body=ix.r(body_id)
    if body<0 or ix.tname(body)!='MANIFOLD_SOLID_BREP':raise ValueError('component requires one source manifold solid')
    faces=[];edges={};vertices={};owners=defaultdict(list);surfaces={}
    for row in document.model.body_faces(body):
        face=int(ix.ids[row]);bounds=refs(ix,face);surface=bounds[-1];loops=[]
        for bound in bounds[:-1]:
            loop_refs=refs(ix,bound)
            if len(loop_refs)!=1 or ix.tname(ix.r(loop_refs[0]))!='EDGE_LOOP':raise ValueError('unsupported component loop')
            loop=loop_refs[0];uses=[]
            for oriented in refs(ix,loop):
                edge_refs=refs(ix,oriented)
                if len(edge_refs)!=1:raise ValueError('non-derived oriented edge endpoints')
                edge=edge_refs[0];start,end,curve=refs(ix,edge)
                kind=ix.tname(ix.r(curve))
                if kind=='B_SPLINE_CURVE_WITH_KNOTS':geometry,_,positions,_=component_spline(document,edge)
                elif kind=='LINE':
                    positions=[]
                    for vertex in (start,end):positions.append(tuple(map(float,exact_point(ix,refs(ix,vertex)[0]))))
                    geometry=VectorCurve.make('line',{'endpoints_mm':positions})
                else:raise ValueError('unsupported component boundary curve: '+kind)
                for vertex,point in zip((start,end),positions):
                    if vertex in vertices and vertices[vertex]!=list(point):raise ValueError('inconsistent source vertex')
                    vertices[vertex]=list(point)
                edges[edge]={'source_curve_id':curve,'vertex_ids':[start,end],'same_sense':sense(ix,edge),
                             'geometry':{'kind':geometry.kind,'parameters':geometry.parameters},'owners':[]}
                owners[edge].append(face);uses.append({'source_use_id':oriented,'source_edge_id':edge,'forward':sense(ix,oriented)})
            loops.append({'source_bound_id':bound,'source_loop_id':loop,'outer':ix.tname(ix.r(bound))=='FACE_OUTER_BOUND',
                          'orientation':sense(ix,bound),'uses':uses})
        kind=ix.tname(ix.r(surface))
        if kind not in ('PLANE','SURFACE_OF_LINEAR_EXTRUSION'):raise ValueError('unsupported component surface: '+kind)
        surfaces[surface]={'kind':kind,'source_reference_ids':list(refs(ix,surface)),
                           'source_record':ix.text(ix.r(surface)).decode().strip()}
        if kind=='SURFACE_OF_LINEAR_EXTRUSION':
            basis,vector=refs(ix,surface);direction=refs(ix,vector)[0]
            basis_geometry=source_bspline_curve(document,basis)
            surfaces[surface]['basis_curve']={'kind':basis_geometry.kind,'parameters':basis_geometry.parameters}
            surfaces[surface]['extrusion_direction_ratios']=[v.decode() for v in scalar_args(ix,ix.r(direction))]
            surfaces[surface]['extrusion_magnitude']=[v.decode() for v in scalar_args(ix,ix.r(vector))]
        else:
            placement=refs(ix,surface)[0]
            surfaces[surface]['source_frame_records']=[ix.text(ix.r(placement)).decode().strip()]+[ix.text(ix.r(v)).decode().strip() for v in refs(ix,placement)]
        faces.append({'source_face_id':face,'source_surface_id':surface,'same_sense':sense(ix,face),'loops':loops})
    for edge,face_ids in owners.items():
        if len(face_ids)!=2:raise ValueError('component boundary is not a two-face manifold')
        edges[edge]['owners']=face_ids
    return {'schema':'rm-source-vector-component-v1','source_sha256':document.source_sha256,'source_body_id':body_id,
            'units':'mm','surfaces':surfaces,'faces':faces,'edges':edges,'vertices_mm':vertices,
            'scope':'complete source-defined component; native surfaces preserved; curve fit substitution is not implied'}


def _native_references(entity,kind):
    getters={'LINE':('Pnt','Dir'),'VECTOR':('Orientation',),'PLANE':('Position',),
             'SURFACE_OF_LINEAR_EXTRUSION':('SweptCurve','ExtrusionAxis'),
             'MANIFOLD_SOLID_BREP':('Outer',),'ADVANCED_FACE':('FaceGeometry',),
             'FACE_OUTER_BOUND':('Bound',),'FACE_BOUND':('Bound',),'ORIENTED_EDGE':('EdgeElement',),
             'EDGE_CURVE':('EdgeStart','EdgeEnd','EdgeGeometry'),'VERTEX_POINT':('VertexGeometry',)}
    if kind=='AXIS2_PLACEMENT_3D':
        result=[entity.Location()]
        if entity.HasAxis():result.append(entity.Axis())
        if entity.HasRefDirection():result.append(entity.RefDirection())
        return result
    if kind=='B_SPLINE_CURVE_WITH_KNOTS':return [entity.ControlPointsListValue(i) for i in range(1,entity.NbControlPointsList()+1)]
    if kind=='CLOSED_SHELL':return [entity.CfsFacesValue(i) for i in range(1,entity.NbCfsFaces()+1)]
    if kind=='EDGE_LOOP':return [entity.EdgeListValue(i) for i in range(1,entity.NbEdgeList()+1)]
    result=[getattr(entity,name)() for name in getters.get(kind,())]
    if kind=='ADVANCED_FACE':result=[entity.BoundsValue(i) for i in range(1,entity.NbBounds()+1)]+result
    if kind not in getters and kind not in ('CARTESIAN_POINT','DIRECTION'):raise ValueError('unsupported native geometry binding: '+kind)
    return result


class NativeComponent:
    """Own a component STEP transfer and explicitly verified source/native maps.

    Record positions are only candidate bindings. Every reachable geometric
    entity's type, ordered references, numeric data and flags are checked before
    any source ID is associated with a transferred native shape.
    """
    def __init__(self,path,body_id):
        from cad_document import CadDocument
        from p21split import forward_closure
        from validate_parts import read_part
        from OCP.STEPConstruct import STEPConstruct
        from OCP.BRepCheck import BRepCheck_Analyzer
        self.document=CadDocument.from_step(path,workers=1,intern_layers=True)
        try:
            self.graph=component_graph(self.document,body_id)
            self.native_document,self.reader,error=read_part(str(path))
            if error:raise ValueError(error)
            reader=self.reader.Reader();model=reader.StepModel();ix=self.document.index
            if model.NbEntities()!=ix.n:raise ValueError('native/source entity count mismatch')
            source_by_entity={model.Value(i+1):int(ix.ids[i]) for i in range(ix.n)}
            if len(source_by_entity)!=ix.n:raise ValueError('native record identity is not bijective')
            closure=forward_closure(ix,[ix.r(body_id)],np.zeros(ix.n,dtype=bool));self.bound={};maximum=0.
            for row in np.flatnonzero(closure):
                row=int(row);source=int(ix.ids[row]);kind=ix.tname(row);entity=model.Value(row+1)
                native_kind=entity.DynamicType().Name().split('_',1)[-1].upper()
                if kind.replace('_','')!=native_kind:raise ValueError('native/source type mismatch')
                actual=[source_by_entity[value] for value in _native_references(entity,kind)]
                if actual!=list(refs(ix,source)):raise ValueError(f'native/source ordered reference mismatch #{source} {kind}: {actual} != {list(refs(ix,source))}')
                pairs=[]
                if kind in ('CARTESIAN_POINT','DIRECTION'):
                    n=entity.NbCoordinates() if kind=='CARTESIAN_POINT' else entity.NbDirectionRatios()
                    native=[entity.CoordinatesValue(i) if kind=='CARTESIAN_POINT' else entity.DirectionRatiosValue(i) for i in range(1,n+1)]
                    pairs.append((np.array(native),np.array(scalar_args(ix,row),dtype=float)))
                if kind=='VECTOR':pairs.append((np.array([entity.Magnitude()]),np.array(scalar_args(ix,row),dtype=float)))
                if kind=='B_SPLINE_CURVE_WITH_KNOTS':
                    args=split_arguments(ix.text(row).split(b'=',1)[1])
                    if entity.Degree()!=int(args[1]):raise ValueError('native/source spline degree mismatch')
                    import re
                    numbers=rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?'
                    native_knots=[entity.KnotsValue(i) for i in range(1,entity.NbKnots()+1)]
                    pairs.append((np.array(native_knots),np.array(re.findall(numbers,args[7]),dtype=float)))
                    if [entity.KnotMultiplicitiesValue(i) for i in range(1,entity.NbKnotMultiplicities()+1)]!=list(map(int,re.findall(rb'\d+',args[6]))):raise ValueError('native/source spline multiplicity mismatch')
                if kind in ('ADVANCED_FACE','EDGE_CURVE') and bool(entity.SameSense())!=sense(ix,source):raise ValueError('native/source sense mismatch')
                if kind in ('FACE_OUTER_BOUND','FACE_BOUND','ORIENTED_EDGE') and bool(entity.Orientation())!=sense(ix,source):raise ValueError('native/source orientation mismatch')
                for a,b in pairs:
                    if a.shape!=b.shape or not np.isfinite(a).all():raise ValueError('native/source numeric shape mismatch')
                    error=float(np.max(abs(a-b),initial=0));maximum=max(maximum,error)
                    if error>1e-10:raise ValueError('native/source numeric mismatch')
                self.bound[source]=entity
            process=reader.WS().MapReader()
            self.shape=STEPConstruct.FindShape_s(process,self.bound[body_id])
            if self.shape.IsNull() or not BRepCheck_Analyzer(self.shape).IsValid():raise ValueError('native source solid is invalid')
            self.shapes={source:STEPConstruct.FindShape_s(process,self.bound[source]) for source in
                         [body_id]+[f['source_face_id'] for f in self.graph['faces']]+list(self.graph['edges'])+list(self.graph['vertices_mm'])}
            if any(shape.IsNull() for shape in self.shapes.values()):raise ValueError('source topology transfer missing')
            self.proof={'geometry_entities_checked':int(closure.sum()),'max_numeric_decode_difference':maximum,
                        'source_native_incidence_verified':True,'valid_source_solid':True}
        except BaseException:
            self.document.close();raise

    def close(self):self.document.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def mesh(self,linear_mm=.1,angular_rad=.2):
        """Mesh one complete solid and weld only source-identical boundary uses.

        Shared edge samples are registered once and checked across both incident
        faces. Coincident unrelated vertices are never position-welded.
        """
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepTools import BRepTools
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopAbs import TopAbs_FACE,TopAbs_REVERSED
        from OCP.TopExp import TopExp_Explorer
        if not np.isfinite([linear_mm,angular_rad]).all() or min(linear_mm,angular_rad)<=0:raise ValueError('invalid native mesh settings')
        BRepTools.Clean_s(self.shape);BRepMesh_IncrementalMesh(self.shape,linear_mm,False,angular_rad,False)
        face_shapes=[];explorer=TopExp_Explorer(self.shape,TopAbs_FACE)
        while explorer.More():face_shapes.append(TopoDS.Face(explorer.Current()));explorer.Next()
        positions=[];indices={};triangles=[];face_ids=[];edge_samples={};hits=0;max_seam=0.
        def vertex(key,point):
            nonlocal max_seam
            if key in indices:
                error=float(np.linalg.norm(positions[indices[key]]-point));max_seam=max(max_seam,error)
                if error>1e-6:raise ValueError('shared source boundary mismatch')
            else:indices[key]=len(positions);positions.append(np.array(point))
            return indices[key]
        for record in self.graph['faces']:
            source=record['source_face_id'];matches=[shape for shape in face_shapes if shape.IsSame(self.shapes[source])]
            if len(matches)!=1:raise ValueError('native transfer changed face topology')
            face=matches[0];location=TopLoc_Location();tri=BRep_Tool.Triangulation_s(face,location)
            if tri is None or tri.NbTriangles()==0:raise ValueError('unmeshed source face')
            points=np.array([tri.Node(i).Transformed(location.Transformation()).Coord() for i in range(1,tri.NbNodes()+1)])
            boundary={}
            for loop in record['loops']:
                for use in loop['uses']:
                    edge=use['source_edge_id'];edge_shape=TopoDS.Edge(self.shapes[edge])
                    poly=BRep_Tool.PolygonOnTriangulation_s(edge_shape,tri,location)
                    if poly is None:raise ValueError('shared source edge has no triangulation polygon')
                    nodes=[poly.Node(i)-1 for i in range(1,poly.NbNodes()+1)]
                    start,end=self.graph['edges'][edge]['vertex_ids'];origin=np.array(self.graph['vertices_mm'][start])
                    if np.linalg.norm(points[nodes[-1]]-origin)<np.linalg.norm(points[nodes[0]]-origin):nodes.reverse()
                    samples=points[nodes]
                    if edge in edge_samples:
                        if edge_samples[edge].shape!=samples.shape or np.max(np.linalg.norm(edge_samples[edge]-samples,axis=1))>1e-6:raise ValueError('incident faces sampled shared edge differently')
                        hits+=1
                    else:edge_samples[edge]=samples
                    for i,node in enumerate(nodes):
                        key=('vertex',start) if i==0 else ('vertex',end) if i==len(nodes)-1 else ('edge',edge,i)
                        index=vertex(key,points[node])
                        if node in boundary and boundary[node]!=index:raise ValueError('inconsistent boundary vertex ownership')
                        boundary[node]=index
            mapping=[boundary[i] if i in boundary else vertex(('face',source,i),p) for i,p in enumerate(points)]
            for i in range(1,tri.NbTriangles()+1):
                corners=[mapping[n-1] for n in tri.Triangle(i).Get()]
                if face.Orientation()==TopAbs_REVERSED:corners[1],corners[2]=corners[2],corners[1]
                triangles.append(corners);face_ids.append(source)
        positions=np.array(positions);triangles=np.array(triangles,dtype=np.uint32)
        incidence=Counter(tuple(sorted((int(a),int(b)))) for t in triangles for a,b in zip(t,np.roll(t,-1)))
        directed=Counter((int(a),int(b)) for t in triangles for a,b in zip(t,np.roll(t,-1)))
        if any(count!=2 for count in incidence.values()) or any(directed[a,b]!=directed[b,a] for a,b in incidence):raise ValueError('exported component mesh is not closed and consistently oriented')
        return positions,triangles,np.array(face_ids),{'faces':len(self.graph['faces']),'source_edges':len(edge_samples),
                'shared_edge_cache_hits':hits,'max_shared_boundary_difference_mm':max_seam,'vertices':len(positions),
                'triangles':len(triangles),'closed_oriented_manifold':True,'linear_deflection_mm':linear_mm,'angular_deflection_rad':angular_rad,
                'scope':'native source tessellation; mesher deflection settings are not a formal continuous error certificate'}
