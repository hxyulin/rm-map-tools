# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Finite planar patches factored into shared affine quad/triangle templates.

This optional source-backed layer retains topology, appearance and component
ownership per use. It bounds straight-boundary normalization; it does not certify
native healed faces, merge solids or remove unsupported geometry.
"""
from dataclasses import dataclass
from fractions import Fraction
import math

import numpy as np
from cad_patch_matching import polygon_patch,exact_point,scalar_args,sub,dot,cross
from cad_shape_fitting import simplify_polygon


TEMPLATES = {
    'quad': (np.array([[0.,0,0],[1,0,0],[1,1,0],[0,1,0]]), np.array([[0,1,2],[0,2,3]],dtype=np.uint32)),
    'triangle': (np.array([[0.,0,0],[1,0,0],[0,1,0]]), np.array([[0,1,2]],dtype=np.uint32)),
}
for positions,triangles in TEMPLATES.values():
    positions.flags.writeable=False;triangles.flags.writeable=False


def source_incidence(patch):
    """Bound original vertex-to-plane/line distances using exact decimal algebra.

    Reject self-intersecting projected trims. Distances measure source incidence
    inconsistencies separately from the proposed finite polygon normalization.
    """
    ix=patch.document.index
    frame=int(ix.refs_of(ix.r(patch.surface_id))[0]);refs=ix.refs_of(ix.r(frame))
    origin=exact_point(ix,int(refs[0]));normal=exact_point(ix,int(refs[1])) if len(refs)>1 else (Fraction(0),Fraction(0),Fraction(1))
    norm2=dot(normal,normal)
    if norm2<=0:raise ValueError('zero source normal')
    plane=max(math.sqrt(float(dot(sub(p,origin),normal)**2/norm2)) for p in patch.points)
    line=0.
    for i,edge in enumerate(patch.edge_ids):
        curve=int(ix.refs_of(ix.r(edge))[2]);base,vector=map(int,ix.refs_of(ix.r(curve)))
        direction=exact_point(ix,int(ix.refs_of(ix.r(vector))[0]));magnitude=scalar_args(ix,ix.r(vector))
        if dot(direction,direction)<=0 or len(magnitude)!=1 or Fraction(magnitude[0].decode())<=0:
            raise ValueError('invalid source line direction/magnitude')
        point=exact_point(ix,base)
        for endpoint in (patch.points[i],patch.points[(i+1)%len(patch.points)]):
            residual=cross(sub(endpoint,point),direction)
            line=max(line,math.sqrt(float(dot(residual,residual)/dot(direction,direction))))
    drop=max(range(3),key=lambda k:abs(normal[k]))
    q=[tuple(v for k,v in enumerate(p) if k!=drop) for p in patch.points]
    def side(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,p):return all(min(a[k],b[k])<=p[k]<=max(a[k],b[k]) for k in (0,1))
    for i,(a,b) in enumerate(zip(q,q[1:]+q[:1])):
        for j in range(i+1,len(q)):
            if j==i+1 or (i==0 and j==len(q)-1):continue
            c,d=q[j],q[(j+1)%len(q)];values=(side(a,b,c),side(a,b,d),side(c,d,a),side(c,d,b))
            if values[0]*values[1]<0 and values[2]*values[3]<0 or any(not z and on(x,y,p) for z,x,y,p in
                ((values[0],a,b,c),(values[1],a,b,d),(values[2],c,d,a),(values[3],c,d,b))):
                raise ValueError('self-intersecting source polygon')
    n=np.array(normal,float);n/=np.linalg.norm(n)
    if not patch.orientations[0]:n=-n
    return n,plane+line


@dataclass(frozen=True)
class AffinePatchUse:
    """One finite template instance with all original source-boundary identities.

    frame_mm stores origin, u and v as rows, in source millimetres. Original
    edge subdivisions remain provenance; adjacent owners are never welded or
    assigned independent collision semantics by this representation pass.
    """
    source_face_id: int
    component_id: str
    template: str
    frame_mm: tuple
    source_vertex_ids: tuple
    source_edge_ids: tuple
    source_oriented_edge_ids: tuple
    orientations: tuple
    retained_corner_indices: tuple
    boundary_error_bound_mm: float
    source_incidence_error_mm: float
    simplification_error_mm: float
    corner_reconstruction_error_mm: float
    numeric_guard_mm: float
    source_colour: str | None = None
    appearance_target_id: int | None = None
    collision_role: str = 'structural'

    def positions_mm(self):
        """Expand the shared template through this use's independent affine frame."""
        origin,u,v=np.array(self.frame_mm)
        positions,_=TEMPLATES[self.template]
        return origin+positions[:,0,None]*u+positions[:,1,None]*v

    def matrix_m(self):
        """Return a proper nonsingular glTF instance transform into source metres."""
        origin,u,v=np.array(self.frame_mm);normal=np.cross(u,v);normal/=np.linalg.norm(normal)
        matrix=np.eye(4);matrix[:3,:3]=np.column_stack((u/1000,v/1000,normal));matrix[:3,3]=origin/1000
        return matrix


def affine_patch(patch,*,component_id,budget_mm=1e-6,source_colour=None,appearance_target_id=None,collision_role='structural'):
    """Normalize a finite triangle/parallelogram within a complete boundary budget.

    No quantized hash authorizes reuse. Original straight boundary chains have
    monotone chord correspondence. Surviving corners are source-anchored except
    the two corners affected by orthogonal quad reconstruction, whose displacement
    is charged explicitly.
    Source support-incidence error and floating guard also consume the budget.
    This is a finite source-polyline bound, not native surface equivalence.
    """
    if not math.isfinite(budget_mm) or budget_mm<=0:raise ValueError('invalid patch budget')
    points=patch.coordinates();guard=max(1e-8,float(np.spacing(abs(points).max()))*64)
    normal,incidence=source_incidence(patch)
    if incidence+guard>=budget_mm:raise ValueError('source incidence exceeds patch budget')
    corners,reduction=simplify_polygon(points,(budget_mm-incidence-guard)/4)
    if len(corners) not in (3,4):raise ValueError('finite polygon is not a triangle/parallelogram template')
    keep=list(reduction['corner_indices'])
    if np.cross(corners[1]-corners[0],corners[-1]-corners[0])@normal<0:
        keep=[keep[0]]+keep[:0:-1];corners=points[keep]
    origin=corners[0];u=corners[1]-origin;v=corners[-1]-origin
    normal2=np.cross(u,v);area=np.linalg.norm(normal2)
    if min(np.linalg.norm(u),np.linalg.norm(v),area/max(np.linalg.norm(u),np.linalg.norm(v),1e-30))<=100*budget_mm:
        raise ValueError('template feature too small for patch budget')
    turns=[np.cross(corners[(i+1)%len(corners)]-p,corners[(i+2)%len(corners)]-corners[(i+1)%len(corners)])@normal
           for i,p in enumerate(corners)]
    if min(turns)<=0:raise ValueError('template requires a convex source boundary')
    template='quad' if len(corners)==4 else 'triangle'
    if template=='quad':
        # Keep glTF/Bevy placements decomposable to rotation and scale. Genuine
        # sheared quads remain in the original source fallback.
        v=v-u*float((u@v)/(u@u))
        predicted=np.array([origin,origin+u,origin+u+v,origin+v])
        correction=float(np.linalg.norm(predicted-corners,axis=1).max())
    else:correction=0.
    chain=reduction['continuous_chain_error_bound_source_units']
    bound=incidence+chain+correction+guard
    if bound>budget_mm:raise ValueError('affine corner reconstruction exceeds patch budget')
    return AffinePatchUse(patch.face_id,component_id,template,tuple(tuple(float(x) for x in row) for row in (origin,u,v)),
                          patch.vertex_ids,patch.edge_ids,patch.oriented_edge_ids,patch.orientations,tuple(keep),
                          bound,incidence,chain,correction,guard,source_colour,appearance_target_id,collision_role)


@dataclass(frozen=True)
class PatchInstanceLayer:
    """Optional affine templates plus an explicit fallback for every other face."""
    source_sha256: str
    budget_mm: float
    uses: tuple
    fallback_face_ids: tuple
    rejection_counts: tuple
    source_face_count: int

    def statistics(self):
        """Report geometry/frame bytes without confusing sharing with placed draws.

        Byte counts cover finite polygon positions and instance frames only;
        provenance, source fallback graphs, appearance and Python memory are
        excluded from both sides. All source edge identities remain per use.
        """
        from collections import Counter
        kinds=Counter(u.template for u in self.uses)
        before=sum(len(u.source_vertex_ids)*3*8 for u in self.uses)
        frames=len(self.uses)*9*8
        prototypes=sum(TEMPLATES[k][0].nbytes for k in kinds)
        return {'source_faces':self.source_face_count,'accepted_face_uses':len(self.uses),
                'retained_fallback_faces':len(self.fallback_face_ids),'template_definitions':len(kinds),
                'uses_by_template':dict(kinds),'original_polygon_position_bytes':before,
                'affine_frame_and_template_position_bytes':frames+prototypes,
                'source_polygon_minimum_triangle_count':sum(len(u.source_vertex_ids)-2 for u in self.uses),
                'template_triangle_uses':sum(len(TEMPLATES[u.template][1]) for u in self.uses),
                'max_boundary_error_bound_mm':max((u.boundary_error_bound_mm for u in self.uses),default=0.),
                'unresolved_direct_diffuse_appearance_uses':sum(u.source_colour is None for u in self.uses),
                'scope':'definition-level finite planar patches; no whole-field/runtime triangle or GPU draw reduction claimed; frame/position bytes exclude shared provenance and source fallback'}


def build_patch_instances(document,hierarchy,*,roles=None,budget_mm=1e-6):
    """Build bounded finite instances while preserving every rejected source face.

    Affine dimensions and shear are per-use parameters. Two templates do not
    imply that all quads/triangles have identical dimensions or contact owners.
    Source metadata, native CAD and installed exports remain immutable.
    """
    from collections import Counter
    if not math.isfinite(budget_mm) or budget_mm<=0:raise ValueError('invalid patch budget')
    if hierarchy.get('files_sha256',{}).get('field.step')!=document.source_sha256:
        raise ValueError('patch instance hierarchy/source mismatch')
    if set(document.geometry_length_units)!={'.MILLI.,.METRE.'}:
        raise ValueError('patch instance bounds require millimetres')
    if roles and roles.source_sha256!=document.source_sha256:raise ValueError('patch instance role/source mismatch')
    ix=document.index;seen=set();uses=[];fallback=[];rejections=Counter()
    for component in hierarchy['components']:
        members=set(component['face_ids'])
        if seen & members:raise ValueError('overlapping source component face ownership')
        seen.update(members);appearance={}
        for body in component['export_body_ids'].values():
            row=ix.r(int(body))
            for face,shell in document.model.body_faces_shells(row):
                source=int(ix.ids[face])
                if source not in members:continue
                for target in (face,shell,row):
                    if target<0:continue
                    color=document.model.surface_colour(target)
                    if color is not None:
                        appearance[source]=(color,int(ix.ids[target]));break
        role=roles.binding(component['id']) if roles else None
        marking_faces=set(role['source_face_ids']) if role else set()
        for source in component['face_ids']:
            try:
                patch=polygon_patch(document,source)
                color,target=appearance.get(source,(None,None))
                use=affine_patch(patch,component_id=component['id'],budget_mm=budget_mm,
                                 source_colour=color,appearance_target_id=target,
                                 collision_role='marking' if source in marking_faces else 'structural')
            except ValueError as error:
                fallback.append(source);rejections[str(error)]+=1;continue
            uses.append(use)
    actual_faces={int(ix.ids[row]) for row in ix.rows_of('ADVANCED_FACE')}
    if len(seen)!=hierarchy['source_face_definitions'] or seen!=actual_faces:
        raise ValueError('incomplete source face accounting')
    if len(uses)+len(fallback)!=len(seen):raise ValueError('patch instance coverage mismatch')
    document.verify_source()
    return PatchInstanceLayer(document.source_sha256,budget_mm,tuple(uses),tuple(fallback),tuple(rejections.items()),len(seen))
