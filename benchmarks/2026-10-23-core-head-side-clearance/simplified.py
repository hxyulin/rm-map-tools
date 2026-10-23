"""Sharp trapezoid recesses in thin side panels, native convex frame pieces."""
import json,sys
import numpy as np
from scipy.spatial import ConvexHull
from shapely.geometry import Polygon
from shapely import constrained_delaunay_triangles
from shapely.ops import unary_union
from review import b,original_envelopes,KEEP
b.OUT=b.ROOT/'out/rmuc2027-core-head-side-clearance-simple'

def panel(nodes,node):
    t=nodes[node];cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);k=np.linalg.norm(cross,axis=1).argmax();normal=cross[k]/np.linalg.norm(cross[k])
    if normal[2]<0:normal=-normal
    # Positive-Z face of the exact 2 mm plate.
    offsets=t.reshape(-1,3)@normal;offset=offsets.max()
    mask=np.max(abs(t@normal-offset),axis=1)<.01
    source=unary_union([Polygon(q[:,:2])for q in t[mask]]).buffer(.01).buffer(-.01)
    assert source.geom_type=='Polygon'and len(source.interiors)==1
    if node==1254:
        outer=[[-838.64,-1114.59],[-838.64,-812.37],[-666.55,-763.83],[-666.55,-1163.13]]
        hole=[[-823.68,-1097.89],[-681.51,-1059.70],[-681.51,-867.26],[-823.68,-829.07]]
    else:
        outer=[[-560.59,-1163.13],[-560.59,-763.83],[-387.69,-812.37],[-387.69,-1114.59]]
        hole=[[-402.73,-1097.89],[-545.55,-1059.70],[-545.55,-867.26],[-402.73,-829.07]]
    region=Polygon(outer,[hole]);assert region.is_valid
    pieces=list(constrained_delaunay_triangles(region).geoms)
    # Merge adjacent triangles whenever the result is one convex piece.
    changed=True
    while changed:
        changed=False
        for i in range(len(pieces)):
            for j in range(i+1,len(pieces)):
                union=pieces[i].union(pieces[j]);hull=union.convex_hull
                if union.geom_type=='Polygon'and hull.area-union.area<1e-6:
                    pieces=[q for k,q in enumerate(pieces)if k not in [i,j]]+[hull];changed=True;break
            if changed:break
    assert unary_union(pieces).symmetric_difference(region).area<1e-5
    shapes=[]
    for piece in pieces:
        xy=np.array(piece.exterior.coords)[:-1];z=(offset-xy@normal[:2])/normal[2]
        face=np.column_stack([xy,z]);pts=np.concatenate([face,face-normal*2]);center=pts.mean(0)
        shapes.append(dict(kind='convex_hull',vertices_local_m=((pts-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1])))
    return shapes,dict(source_node=node,normal=normal.tolist(),front_plane_offset_mm=float(offset),thickness_mm=2,outer_xy_mm=outer,hole_xy_mm=hole,convex_pieces=len(pieces),
        source_hole_area_xy_mm2=Polygon(source.interiors[0]).area,new_hole_area_xy_mm2=Polygon(hole).area,
        hole_boundary_hausdorff_xy_mm=float(Polygon(hole).boundary.hausdorff_distance(Polygon(source.interiors[0]).boundary)),
        caveat='Sharp trapezoid approximates the large opening; small corner and perimeter differences are deliberate.')

def envelopes(nodes,variant):
    shapes,definition=original_envelopes(nodes,'balanced');pairs=[(s,label)for s,label in zip(shapes,definition['labels'])if label not in ['left body','right body','lower end bridge','upper end bridge']]
    shapes=[s for s,label in pairs];labels=[label for s,label in pairs];panels=[]
    for node in [1254,1255]:
        new,proof=panel(nodes,node);shapes+=new;labels+=['simplified recessed side panel']*len(new);panels.append(proof)
    definition.update(labels=labels,simplified_side_panels=panels,retained_original_outer_casing_nodes=[108,1266,1268],deliberate_changes=['Large side cutouts kept as sharp trapezoids in 2 mm plates.','Original top/bottom/front casing retained. Internal mechanisms use coarse boxes.'])
    return shapes,definition
b.envelopes=envelopes
if __name__=='__main__':
    action=sys.argv[1]if len(sys.argv)>1 else 'build'
    if action=='build':b.main(variants=['side-clearance-simple'],keep_override=KEEP-{1254,1255})
    elif action in ['verify','render']:b.p.module('simple_side_'+action,str(b.ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff'/action)+'.py').main()
    else:raise ValueError(action)
