# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only source-graph discovery of mounting openings and possible hardware.

Analytic supports and explicit topology provide evidence, not equipment semantics
or permission to remove geometry. No native import, tessellation or healing.
"""
from collections import Counter,defaultdict
from functools import lru_cache
import math
import re
import numpy as np
from cad_patch_matching import scalar_args,sense
from p21model import BODY_TYPES

HARDWARE_NAME=re.compile(r'螺[钉栓母丝]|垫[圈片]|(?:\b(?:bolt|screw|nut|washer|DIN\s*\d+|ISO\s*\d+)\b)',re.I)


class AnalyticDetails:
    """Source-scoped analytic frames, finite edge bounds and circular loop checks."""
    def __init__(self,document):
        self.document=document;self.ix=document.index
        for name in ('point','frame','radial','edge'):setattr(self,name,lru_cache(maxsize=None)(getattr(self,name)))

    def refs(self,entity,kind=None):
        row=self.ix.r(int(entity))
        if row<0 or kind and self.ix.tname(row)!=kind:raise ValueError('unsupported or unresolved '+str(kind or 'entity'))
        return tuple(map(int,self.ix.refs_of(row)))

    def point(self,entity):
        row=self.ix.r(entity)
        if row<0 or self.ix.tname(row) not in ('CARTESIAN_POINT','DIRECTION'):raise ValueError('unsupported coordinate')
        v=np.array([float(x) for x in scalar_args(self.ix,row)])
        if v.shape!=(3,) or not np.isfinite(v).all():raise ValueError('nonfinite/non-3D coordinate')
        return v

    def frame(self,placement):
        self.refs(placement,'AXIS2_PLACEMENT_3D')
        fields=re.fullmatch(rb"\s*'(?:[^']|'')*'\s*,\s*#(\d+)\s*,\s*(\$|#\d+)\s*,\s*(\$|#\d+)\s*",self.ix.args(self.ix.r(placement)))
        if not fields:raise ValueError('unsupported axis placement syntax')
        location,axis,reference=fields.groups();origin=self.point(int(location));normal=self.point(int(axis[1:])).copy() if axis!=b'$' else np.array([0.,0,1])
        if reference==b'$' and np.linalg.norm(np.cross(normal,[0,0,1]))>1e-10:raise ValueError('unresolved implicit nonaxial reference direction')
        x=self.point(int(reference[1:])).copy() if reference!=b'$' else np.array([1.,0,0])
        if min(np.linalg.norm(normal),np.linalg.norm(x))<1e-12:raise ValueError('zero frame axis')
        normal/=np.linalg.norm(normal);x/=np.linalg.norm(x)
        if abs(normal@x)>1e-6:raise ValueError('nonorthogonal frame')
        x-=normal*(normal@x);x/=np.linalg.norm(x)
        return origin,normal,x,np.cross(normal,x)

    def radial(self,surface):
        row=self.ix.r(surface)
        if row<0 or self.ix.tname(row) not in ('CIRCLE','CYLINDRICAL_SURFACE'):raise ValueError('unsupported radial support')
        refs=self.refs(surface);numbers=scalar_args(self.ix,row)
        if len(refs)!=1 or len(numbers)!=1:raise ValueError('unsupported radial parameters')
        radius=float(numbers[0])
        if not math.isfinite(radius) or radius<=0:raise ValueError('invalid radius')
        return (*self.frame(refs[0]),radius)

    def edge(self,edge):
        refs=self.refs(edge,'EDGE_CURVE')
        if len(refs)!=3:raise ValueError('unsupported finite edge')
        start,end,curve=refs;vertices=[]
        for vertex in [start,end]:
            values=self.refs(vertex,'VERTEX_POINT')
            if len(values)!=1:raise ValueError('unsupported vertex')
            vertices.append(self.point(values[0]))
        kind=self.ix.tname(self.ix.r(curve));visited=set()
        while kind in ('SURFACE_CURVE','SEAM_CURVE'):
            if curve in visited:raise ValueError('cyclic boundary support')
            visited.add(curve);refs=self.refs(curve)
            if not refs:raise ValueError('missing 3D curve support')
            curve=refs[0];kind=self.ix.tname(self.ix.r(curve))
        if kind=='LINE':return start,end,curve,np.array(vertices),None
        if kind!='CIRCLE':raise ValueError('nonanalytic boundary curve')
        center,axis,x,y,radius=self.radial(curve);extent=radius*np.sqrt(np.maximum(0,1-axis**2));bounds=np.array([*vertices,center-extent,center+extent]);angles=[]
        for point in vertices:
            delta=point-center
            if abs(delta@axis)>1e-5 or abs(np.linalg.norm(delta)-radius)>1e-5:raise ValueError('circle endpoint off support')
            angles.append(math.atan2(delta@y,delta@x))
        forward=sense(self.ix,edge);span=((angles[1]-angles[0]) if forward else (angles[0]-angles[1]))%(2*math.pi)
        if start==end:span=2*math.pi
        elif span<1e-10:raise ValueError('ambiguous zero arc')
        return start,end,curve,bounds,(center,axis,radius,span,forward)

    def loop(self,loop):
        uses=self.refs(loop,'EDGE_LOOP')
        if not uses:raise ValueError('empty loop')
        edges=[];ends=[];begins=[];bounds=[];circles=[]
        for use in uses:
            refs=self.refs(use,'ORIENTED_EDGE')
            if len(refs)!=1:raise ValueError('unsupported oriented edge')
            edge=refs[0];a,b,curve,box,circle=self.edge(edge);forward=sense(self.ix,use);begins.append(a if forward else b);ends.append(b if forward else a);edges.append(edge);bounds.append(box)
            if circle:circles.append((circle,forward))
        if any(ends[i]!=begins[(i+1)%len(uses)] for i in range(len(uses))):raise ValueError('disconnected/open trim loop')
        circular=None
        if len(circles)==len(uses):
            center,axis,radius,_,_=circles[0][0];signed=[];valid=True
            for (c,n,r,span,support_forward),use_forward in circles:
                if np.linalg.norm(c-center)>1e-5 or abs(r-radius)>1e-5 or abs(n@axis)<1-1e-8:valid=False;break
                signed.append(span*(1 if support_forward==use_forward else -1)*(1 if n@axis>0 else -1))
            if valid and abs(abs(sum(signed))-2*math.pi)<1e-6 and abs(sum(abs(v) for v in signed)-2*math.pi)<1e-6:circular=(center,axis,radius)
        return edges,np.concatenate(bounds),circular


def mounting_details(document,*,maximum_diameter_mm=17,maximum_fastener_length_mm=60,maximum_slot_length_mm=60):
    """Audit every source body/shell with configurable millimetre discovery budgets.

    Circular openings need explicit planar inner topology and a connected complete
    analytic circle, including split arcs. Other line/circle loops are narrow
    opening candidates. Possible fasteners require bounded analytic edges and
    coaxial cylindrical supports; names provide a separate semantic hint only.
    Counts are definitions/opening mouths, never estimated triangle savings.
    """
    budgets=(maximum_diameter_mm,maximum_fastener_length_mm,maximum_slot_length_mm)
    if not all(math.isfinite(v) and v>0 for v in budgets):raise ValueError('invalid mounting discovery budget')
    if set(document.geometry_length_units)!={'.MILLI.,.METRE.'}:raise ValueError('mounting detail budgets require explicit millimetre geometry')
    ix=document.index;model=document.model;analytic=AnalyticDetails(document);face_owners=defaultdict(set);units=defaultdict(lambda:{'faces':set(),'bodies':set(),'products':set()});body_products=defaultdict(set)
    for body in ix.rows_of(*BODY_TYPES):body_products[int(body)]
    for body,rep in model.bodies:
        product=model.rep_product.get(rep)
        if product is not None:body_products[body].add(product)
    for body in sorted(body_products):
        for face,shell in model.body_faces_shells(body):
            face_owners[face].add(body);key=(shell if shell>=0 else body);units[key]['faces'].add(face);units[key]['bodies'].add(body);units[key]['products'].update(body_products[body])
    def owners(bodies):
        products={p for body in bodies for p in body_products[body]}
        return {'source_body_ids':sorted(int(ix.ids[b]) for b in bodies),'owner_products':[{'source_product_id':int(ix.ids[p]),'name':model.pname(p)} for p in sorted(products)]}
    openings=[];skipped=Counter();families=defaultdict(list)
    for face in sorted(face_owners):
        refs=analytic.refs(int(ix.ids[face]));surface=refs[-1]
        if ix.tname(ix.r(surface))!='PLANE':continue
        outer=[b for b in refs[:-1] if ix.tname(ix.r(b))=='FACE_OUTER_BOUND'];inner=[b for b in refs[:-1] if ix.tname(ix.r(b))=='FACE_BOUND']
        if not inner:continue
        if len(outer)!=1:skipped['ambiguous planar outer bound']+=len(inner);continue
        try:
            plane_ref=analytic.refs(surface,'PLANE')
            if len(plane_ref)!=1:raise ValueError('unsupported plane')
            plane_origin,normal,x,y=analytic.frame(plane_ref[0])
        except ValueError as error:skipped[str(error)]+=len(inner);continue
        for bound in inner:
            try:
                loop_ref=analytic.refs(bound,'FACE_BOUND')
                if len(loop_ref)!=1:raise ValueError('unsupported inner bound')
                edges,bounds,circle=analytic.loop(loop_ref[0])
                for edge in edges:
                    _,_,_,box,c=analytic.edge(edge)
                    if c:
                        center,axis,_,_,_=c
                        if abs(normal@axis)<1-1e-8 or abs((center-plane_origin)@normal)>1e-5:raise ValueError('boundary circle off owning plane')
                    elif abs((box-plane_origin)@normal).max()>1e-5:raise ValueError('boundary line off owning plane')
                entry={'source_face_id':int(ix.ids[face]),'source_bound_id':bound,'source_loop_id':loop_ref[0],'source_edge_ids':edges,**owners(face_owners[face])}
                if circle:
                    center,axis,radius=circle
                    if abs(normal@axis)<1-1e-8 or abs((center-plane_origin)@normal)>1e-5:raise ValueError('circle not in owning plane')
                    if radius*2>=maximum_diameter_mm:skipped['circular opening outside diameter budget']+=1;continue
                    entry.update(kind='circular-opening',diameter_mm=2*radius,center_mm=center.tolist(),axis_direction=axis.tolist(),evidence='Explicit inner bound; connected full circle on planar face, not a confirmed mounting role.')
                    canonical=axis*(1 if axis[np.argmax(abs(axis))]>=0 else -1);anchor=center-canonical*(center@canonical);key=(tuple(sorted(face_owners[face])),tuple(np.round(np.r_[anchor,canonical,radius],5)));families[key].append(len(openings))
                else:
                    # Conservative finite bounds: each trimmed arc contributes its whole circle.
                    # Try face axes and straight-edge directions as planar calipers.
                    directions=[x,y]
                    for edge in edges:
                        a,b,curve,box,c=analytic.edge(edge)
                        if c is None and np.linalg.norm(box[1]-box[0])>1e-10:directions.append((box[1]-box[0])/np.linalg.norm(box[1]-box[0]))
                    boxes=[]
                    for direction in directions:
                        other=np.cross(normal,direction);size=np.ptp(bounds@np.column_stack((direction,other)),axis=0);boxes.append(sorted(size))
                    width,length=min(boxes,key=lambda v:(v[0],v[1]))
                    if width>=maximum_diameter_mm or length>maximum_slot_length_mm:skipped['noncircular opening outside width/length budget']+=1;continue
                    entry.update(kind='narrow-analytic-opening',width_upper_bound_mm=float(width),length_upper_bound_mm=float(length),bbox_mm=[bounds.min(0).tolist(),bounds.max(0).tolist()],evidence='Explicit connected planar inner line/circle loop; narrow conservative caliper bound, not a confirmed slot/socket role.')
                openings.append(entry)
            except ValueError as error:skipped[str(error)]+=1
    family_records=[]
    for ids in families.values():
        if len(ids)<2:continue
        # Preserve all mouths and owners: coincident/two-sided faces are not physical-hole counts.
        family_records.append({'opening_indices':ids,'source_face_ids':[openings[i]['source_face_id'] for i in ids],'interpretation':'Coaxial analytic opening family only; no through/blind-hole or physical-feature equivalence proof.'})
    fasteners=[];fastener_skipped=Counter()
    for unit,data in sorted(units.items()):
        names=[model.pname(p) or '' for p in data['products']];hint=any(HARDWARE_NAME.search(name) for name in names);faces=sorted(data['faces']);supports=[];all_edges=set();surface_types=Counter()
        if len(faces)>256:fastener_skipped['native unit exceeds 256-face discovery budget']+=1;continue
        try:
            for face in faces:
                refs=analytic.refs(int(ix.ids[face]));surface=refs[-1];kind=ix.tname(ix.r(surface));surface_types[kind]+=1
                if kind=='CYLINDRICAL_SURFACE':supports.append(analytic.radial(surface))
                for bound in refs[:-1]:
                    r=analytic.refs(bound)
                    if len(r)!=1:raise ValueError('unsupported unit bound')
                    edges,_,_=analytic.loop(r[0]);all_edges.update(edges)
            if not supports:fastener_skipped['unit has no analytic cylinder']+=1;continue
            if any(kind not in ('PLANE','CYLINDRICAL_SURFACE','CONICAL_SURFACE') for kind in surface_types):raise ValueError('unsupported hardware surface')
            origin,axis,_,_,radius=supports[0];radii=[]
            for center,direction,x,y,r in supports:
                if r*2>=maximum_diameter_mm:raise ValueError('cylinder outside diameter budget')
                if abs(axis@direction)<1-1e-8 or np.linalg.norm(np.cross(center-origin,axis))>1e-4:raise ValueError('noncoaxial cylinders')
                radii.append(r)
            seed=np.eye(3)[np.argmin(abs(axis))];x=np.cross(axis,seed);x/=np.linalg.norm(x);y=np.cross(axis,x)
            # Whole-circle AABBs overbound diagonal supports, so use exact circle extrema in this axis frame.
            projected=[]
            for edge in all_edges:
                _,_,curve,box,c=analytic.edge(edge)
                if c:
                    center,n,r,span,forward=c;local=np.array([center@x,center@y,center@axis]);ext=r*np.sqrt(np.maximum(0,1-(np.array([x,y,axis])@n)**2));projected.extend([local-ext,local+ext])
                else:projected.extend(box@np.column_stack((x,y,axis)))
            size=np.ptp(projected,axis=0);width=float(max(size[:2]));length=float(size[2])
            if width>=maximum_diameter_mm or length>maximum_fastener_length_mm:raise ValueError('finite unit outside width/length budget')
            fasteners.append({'source_unit_id':int(ix.ids[unit]),'source_unit_type':ix.tname(unit),'source_face_ids':[int(ix.ids[f]) for f in faces],**owners(data['bodies']),'kind':'coaxial-hardware-candidate','source_name_hint':hint,'evidence':['Bounded line/circle trims','Coaxial analytic cylinders','Small transverse size']+(['Source product name mentions hardware'] if hint else []),'radius_values_mm':sorted(set(round(r,8) for r in radii)),'axis_origin_mm':origin.tolist(),'axis_direction':axis.tolist(),'transverse_span_upper_bound_mm':width,'axial_span_upper_bound_mm':length,'axis_frame_span_bounds_mm':size.tolist(),'native_surface_types':dict(surface_types),'semantic_status':'unconfirmed; may be fastener, pin, bushing, hinge or indicator; not removable by classification alone'})
        except ValueError as error:fastener_skipped[str(error)]+=1
    products=defaultdict(lambda:{'opening_mouths':0,'possible_fastener_units':0,'source_product_id':None,'name':None})
    for field,items in [('opening_mouths',openings),('possible_fastener_units',fasteners)]:
        for entry in items:
            for product in entry['owner_products']:
                row=products[product['source_product_id']];row[field]+=1;row['source_product_id']=product['source_product_id'];row['name']=product['name']
    return {'policy':{'maximum_opening_diameter_or_width_mm_exclusive':maximum_diameter_mm,'maximum_slot_length_mm':maximum_slot_length_mm,'maximum_fastener_transverse_span_mm_exclusive':maximum_diameter_mm,'maximum_fastener_length_mm':maximum_fastener_length_mm,'maximum_unit_faces':256},'source_bodies':len(body_products),'unowned_body_definitions':sum(not products for products in body_products.values()),'source_face_definitions':len(face_owners),'source_unit_definitions':len(units),'opening_mouths':len(openings),'circular_opening_mouths':sum(r['kind']=='circular-opening' for r in openings),'narrow_noncircular_opening_mouths':sum(r['kind']!='circular-opening' for r in openings),'coaxial_opening_families':family_records,'possible_fastener_units':len(fasteners),'name_supported_fastener_units':sum(r['source_name_hint'] for r in fasteners),'openings':openings,'fasteners':fasteners,'products':sorted(products.values(),key=lambda r:(-r['opening_mouths']-r['possible_fastener_units'],r['source_product_id'])),'opening_skips':dict(skipped),'fastener_skips':dict(fastener_skipped),'interpretation':'Read-only analytic discovery. Mouths/families are not physical holes; candidates are not confirmed fasteners. Product references may share geometry and are nonadditive. No source/CAD/style/mesh edits or triangle-saving claims.'}
