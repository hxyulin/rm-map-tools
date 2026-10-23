"""User-authorized solid rear block, rod cylinder and rectangular plate."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-core-head-rear-internals'))
import rear
b=rear.b
BASE=ROOT/'out/rmuc2027-core-head-rear-internals/rear-internals/verification.json'
b.OUT=ROOT/'out/rmuc2027-core-head-solid-rear'
old_geometry=b.v.geometry

def geometry(shape):
    if shape['kind']!='cylinder':return old_geometry(shape)
    frame=Rotation.from_quat(shape['pose']['rotation_xyzw']).as_matrix()
    return b.p.cylinder(dict(center_m=shape['pose']['translation_m'],axis_unit_vector=frame[:,2].tolist(),radius_m=shape['radius_m'],length_m=shape['length_m']))
b.v.geometry=geometry

def envelopes(nodes,variant):
    shapes,definition=rear.envelopes(nodes,'rear-internals');labels=definition['labels']
    rear_geos=[geometry(shape)for shape,label in zip(shapes,labels)if label=='consolidated motor housing']
    points=np.concatenate(rear_geos).reshape(-1,3);h=__import__('scipy').spatial.ConvexHull(points);points=points[h.vertices];center=points.mean(0)
    block=dict(kind='convex_hull',vertices_local_m=((points-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1]))
    pairs=[(shape,label)for shape,label in zip(shapes,labels)if label not in ['consolidated motor housing','simple notched backing plate']]
    shapes=[shape for shape,label in pairs];labels=[label for shape,label in pairs]
    plate=definition['backing_plate'];normal=np.array(plate['front_normal']);normal[1]=0;normal/=np.linalg.norm(normal);xaxis=np.array([normal[2],0,-normal[0]]);frame=np.column_stack([xaxis,[0,1,0],normal])
    xy=np.array([-613.1,(-1116.9-683.2)/2]);face=np.r_[xy,(plate['front_plane_offset_mm']-xy@normal[:2])/normal[2]]
    rectangle=dict(kind='box',half_extents_m=[115/normal[2]/2000,433.7/2000,4/1000],pose=dict(translation_m=((face-normal*4)/1000).tolist(),rotation_xyzw=Rotation.from_matrix(frame).as_quat().tolist()))
    # Fixed source longitudinal axis; fit enclosing radial interval to both rod leaves.
    rodpoints=np.concatenate([nodes[1297],nodes[1501]]).reshape(-1,3)
    axis=np.array([-.009354,0,.99995625]);axis/=np.linalg.norm(axis);a,u,v=b.p.basis(axis);projection=np.column_stack([rodpoints@u,rodpoints@v]);mid=(projection.min(0)+projection.max(0))/2
    radius=np.linalg.norm(projection-mid,axis=1).max();axial=rodpoints@axis;center=mid[0]*u+mid[1]*v+axis*(axial.min()+axial.max())/2
    rod=dict(kind='cylinder',radius_m=float(radius/1000),length_m=float(np.ptp(axial)/1000),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=Rotation.from_matrix(np.column_stack([u,v,axis])).as_quat().tolist()))
    shapes.extend([block,rectangle,rod]);labels.extend(['single solid lower block','rectangular backing plate','solid rod cylinder'])
    definition.update(labels=labels,solid_lower_block=dict(source='Convex envelope of preceding ten lower motor housing boxes; fills internal channels/recesses.'),
      rectangular_plate=dict(source_node=81,width_mm=115/normal[2],height_mm=433.7,thickness_mm=8,closes_notch=True,roof_corners_filled=True),
      rod_cylinder=dict(source_nodes=[1297,1501],radius_mm=float(radius),length_mm=float(np.ptp(axial)),solid=True,closes_axial_bore_and_slots=True),
      deliberate_changes=['Lower motor housing channels deliberately filled with one convex solid; upper rear support unchanged.','Backing notch and sloped roof become an enclosing rectangle.','Rod and tip become one solid cylinder; bore/slots intentionally closed.','Large side recess frames, upper rear support and all visuals remain unchanged.'])
    return shapes,definition
b.envelopes=envelopes
if __name__=='__main__':
    action=sys.argv[1]if len(sys.argv)>1 else 'build'
    if action=='build':
        b.main(variants=['solid-rear'],keep_override=rear.s.KEEP-{1254,1255,81,1297,1501})
        path=b.OUT/'solid-rear/verification.json';r=json.loads(path.read_text());r['input_pins'][str(BASE)]=b.scan.digest(BASE);path.write_text(json.dumps(r,indent=2)+'\n')
        rows=json.loads((b.OUT/'variants.json').read_text());rows[0]['sha256']=b.scan.digest(path);(b.OUT/'variants.json').write_text(json.dumps(rows,indent=2)+'\n')
    elif action=='verify':b.p.module('solid_rear_verify',str(ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/verify.py')).main(approach_exempt_labels=['solid rod cylinder','single solid lower block'])
    elif action=='render':b.p.module('solid_rear_render',str(ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff/render.py')).main()
    else:raise ValueError(action)
