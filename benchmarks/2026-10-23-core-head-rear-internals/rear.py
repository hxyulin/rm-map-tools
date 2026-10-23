"""Coarse motor envelope and notched backing plate; keep side recesses."""
import json,sys
import numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/2026-10-23-core-head-side-clearance'))
import simplified as s
b=s.b
BASE=ROOT/'out/rmuc2027-core-head-side-clearance-simple/side-clearance-simple/verification.json'
b.OUT=ROOT/'out/rmuc2027-core-head-rear-internals'
previous_envelopes=s.envelopes

def backing(nodes):
    t=nodes[81];cross=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);normal=cross[np.linalg.norm(cross,axis=1).argmax()];normal/=np.linalg.norm(normal)
    if normal[2]<0:normal=-normal
    offset=(t.reshape(-1,3)@normal).max()
    polys=[np.array([[-670.6,-1116.9],[-555.6,-1116.9],[-555.6,-1094.8],[-670.6,-1094.8]]),
        np.array([[-633.1,-1094.8],[-555.6,-1094.8],[-555.6,-1035.0],[-633.1,-1035.0]]),
        np.array([[-670.6,-1035.0],[-555.6,-1035.0],[-555.6,-716.0],[-613.1,-683.2],[-670.6,-716.0]])]
    shapes=[]
    for xy in polys:
        z=(offset-xy@normal[:2])/normal[2];face=np.column_stack([xy,z]);points=np.concatenate([face,face-normal*8]);center=points.mean(0)
        shapes.append(dict(kind='convex_hull',vertices_local_m=((points-center)/1000).tolist(),pose=dict(translation_m=(center/1000).tolist(),rotation_xyzw=[0,0,0,1])))
    return shapes,dict(source_node=81,front_normal=normal.tolist(),front_plane_offset_mm=float(offset),thickness_mm=8,polygons_xy_mm=[q.tolist()for q in polys],
        retained_notch_xy_mm=[[-670.6,-1094.8],[-633.1,-1035.0]],removed_detail='Rounded corners, small lateral ears at the motor level, fine perimeter steps.')

def envelopes(nodes,variant):
    shapes,definition=previous_envelopes(nodes,'side-clearance-simple')
    pairs=[(shape,label)for shape,label in zip(shapes,definition['labels'])if label!='motor housing with approach clearance']
    shapes=[shape for shape,label in pairs];labels=[label for shape,label in pairs]
    bounds=([-656.5,-871.7,-562.9],[-568.8,-706.5,-487.6]);pieces=[bounds]
    for cut in definition['exact_clearance_cut_boxes_mm']:pieces=[piece for parent in pieces for piece in b.subtract(parent,cut)]
    shapes.extend(b.aabb(*piece)for piece in pieces);labels.extend(['consolidated motor housing']*len(pieces))
    plate,proof=backing(nodes);shapes.extend(plate);labels.extend(['simple notched backing plate']*len(plate))
    definition.update(labels=labels,motor_union_box_before_clearance_cuts_mm=bounds,mechanism_box_bounds_after_cuts_mm=[(np.array(lo).tolist(),np.array(hi).tolist())for lo,hi in pieces],backing_plate=proof,
        deliberate_changes=['Small backing-plate perimeter ears/rounding removed; large notch retained.','Motor stepped outer envelope consolidated; sleeve and nozzle clearance cuts retained.','Prior side recesses and three rear support boxes retained.'])
    return shapes,definition
b.envelopes=envelopes
if __name__=='__main__':
    action=sys.argv[1]if len(sys.argv)>1 else 'build'
    if action=='build':
        b.main(variants=['rear-internals'],keep_override=s.KEEP-{1254,1255,81})
        report=json.loads((b.OUT/'rear-internals/verification.json').read_text());report['input_pins'][str(BASE)]=b.scan.digest(BASE)
        path=b.OUT/'rear-internals/verification.json';path.write_text(json.dumps(report,indent=2)+'\n')
        variants=json.loads((b.OUT/'variants.json').read_text());variants[0]['sha256']=b.scan.digest(path);(b.OUT/'variants.json').write_text(json.dumps(variants,indent=2)+'\n')
    elif action in ['verify','render']:b.p.module('rear_internal_'+action,str(ROOT/'benchmarks/2026-10-23-core-head-coarse-tradeoff'/action)+'.py').main()
    else:raise ValueError(action)
