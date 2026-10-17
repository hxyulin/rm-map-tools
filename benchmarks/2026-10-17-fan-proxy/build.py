#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Fit an authorized hollow rectangular fan proxy and locate all source uses."""
import argparse,itertools,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_rectangular_duct import flanged_duct
from cad_wall_fill import shape_map
from export_field_package import GlbWriter
from plan_cad_lods import digest,build_plan
from validate_parts import read_part
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.gp import gp_Trsf

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);source=ROOT/'out/rmuc2027-equipment-pipeline/fan/body-2717086';prior=json.loads((source/'native.json').read_bytes())
    if digest(source/'source.step')!=prior['source_step_sha256']:raise ValueError('fan source changed')
    doc,reader,error=read_part(str(source/'source.step'))
    if error:raise ValueError(error)
    from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
    from OCP.collections import Sequence_TDF_Label
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);faces=shape_map(XCAFDoc_ShapeTool.GetShape_s(roots.Value(1)),TopAbs_FACE)
    def plane(i):return BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(i))).Plane()
    def vector(direction):return np.array([direction.X(),direction.Y(),direction.Z()])
    def point(p):return np.array([p.X(),p.Y(),p.Z()])
    depth=vector(plane(33).Axis().Direction());width=vector(plane(199).Axis().Direction());width-=depth*(width@depth);width/=np.linalg.norm(width);height=np.cross(depth,width);frame=np.array([depth,width,height])
    def offset(i,axis):
        if abs(abs(vector(plane(i).Axis().Direction())@frame[axis])-1)>1e-8:raise ValueError('fit face no longer follows source frame')
        return float(point(plane(i).Location())@frame[axis])
    front=offset(33,0);interface=offset(67,0);rear=offset(201,0);y0=offset(1108,1);y1=offset(199,1);z0=offset(217,2);z1=offset(494,2);iy0=offset(1103,1);iy1=offset(1281,1);iz0=offset(210,2);iz1=offset(496,2);thickness=np.array([iy0-y0,y1-iy1,iz0-z0,z1-iz1])
    if np.ptp(thickness)>1e-6 or abs(((iy0+iy1)-(y0+y1))/2)>1e-6 or abs(((iz0+iz1)-(z0+z1))/2)>1e-6:raise ValueError('source wall no longer uniformly centred')
    transform=gp_Trsf();transform.SetValues(*np.c_[frame,np.zeros(3)].ravel().tolist());wire=BRepTools.OuterWire_s(TopoDS.Face(faces.FindKey(33)));bounds=Bnd_Box();BRepBndLib.AddOptimal_s(BRepBuilderAPI_Transform(wire,transform,True).Shape(),bounds,False,False);low=point(bounds.CornerMin());high=point(bounds.CornerMax());centre=np.array([rear,(y0+y1)/2,(z0+z1)/2])
    if max(abs((low+high)[1:]/2-centre[1:]))>1e-6:raise ValueError('flange and duct no longer concentric')
    dimensions={'duct_length_mm':interface-rear,'duct_width_mm':y1-y0,'duct_height_mm':z1-z0,'wall_mm':float(thickness.mean()),'flange_width_mm':high[1]-low[1],'flange_height_mm':high[2]-low[2],'flange_thickness_mm':front-interface};local,t,parts=flanged_duct(**dimensions);origin=centre@frame;p=local@frame+origin
    writer=GlbWriter('fan/hollow-proxy',{'version':'2.0','copyright':'DJI / RoboMaster source-derived dimensions; authorized rectangular proxy'})
    for part,name in enumerate(['mounting-frame','rectangular-duct']):writer.add_node(name,p/1000,t[parts==part],[None]*int((parts==part).sum()),extras={'source_product_id':2717102,'source_body_id':2717086,'proxy_part':name,'inspection_only':True})
    writer.write(a.out/'fan-proxy.glb');inspection=GlbWriter('fan/hollow-proxy-inspection',{'version':'2.0','copyright':'DJI / RoboMaster source-derived dimensions; authorized rectangular proxy'})
    for part,name in enumerate(['mounting-frame','rectangular-duct']):inspection.add_node(name,local[:,[1,2,0]]/1000,t[parts==part],[None]*int((parts==part).sum()),extras={'source_body_id':2717086,'proxy_part':name,'inspection_only':True})
    inspection.write(a.out/'fan-proxy-inspection.glb');np.savez(a.out/'geometry.npz',positions_mm=p,triangles=t,part_ids=parts,source_origin_mm=origin,source_frame=frame)
    hp=ROOT/'out/rmuc2027-hierarchy/hierarchy.json';hierarchy=json.loads(hp.read_bytes());plan=build_plan(hierarchy);nodes={n['id']:n for n in plan['nodes']};native=np.load(source/'native.npz');terrain=json.loads((ROOT/'out/rmuc2027-terrain-cost-full/audit.json').read_bytes());floor=next(c for c in terrain['components'] if c['id']=='floor/body-23736');field_centre=np.mean(np.array(floor['bbox_mm']),axis=0)[:2];placements=[]
    for node in plan['nodes']:
        if node['component_id']!='fan/body-2717086':continue
        matrix=np.array(node['world_matrix_mm']);world=native['positions_mm']@matrix[:3,:3].T+matrix[:3,3];ancestors=[];cur=node
        while cur['parent'] is not None:cur=nodes[cur['parent']];ancestors.append(cur['name'])
        low=world.min(0);high=world.max(0);xy=((low+high)/2)[:2]-field_centre
        placements.append({'id':len(placements)+1,'hierarchy_node_id':node['id'],'world_matrix_mm':node['world_matrix_mm'],'centre_field_xy_m':(xy/1000).tolist(),'source_world_bbox_mm':[low.tolist(),high.tolist()],'context':next((s for s in ancestors if s.endswith('high-point-complete')),'standalone fixture')})
    if len(placements)!=10:raise ValueError('fan occurrence count changed')
    edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);_,counts=np.unique(edges,axis=0,return_counts=True)
    if not np.all(counts==2):raise ValueError('proxy material boundary is not manifold')
    report={'source_step_sha256':prior['source_step_sha256'],'hierarchy_sha256':digest(hp),'native_face_indices':{'flange_front':33,'flange_back':67,'duct_rear':201,'outer_width':[1108,199],'inner_width':[1103,1281],'outer_height':[217,494],'inner_height':[210,496]},'dimensions':dimensions,'source_frame_rows':frame.tolist(),'source_origin_mm':origin.tolist(),'before_triangles_per_fan':40666,'after_triangles_per_fan':len(t),'triangles_by_part':np.bincount(parts).tolist(),'placed_uses':len(placements),'placed_triangles':len(t)*len(placements),'placed_saving_vs_approved':(40666-len(t))*len(placements),'two_manifold_material_boundary':True,'field_centre_source_xy_mm':field_centre.tolist(),'placements':placements,'outputs_sha256':{name:digest(a.out/name) for name in ['fan-proxy.glb','fan-proxy-inspection.glb','geometry.npz']},'producer_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_rectangular_duct.py']},'scope':'User-authorized thick rectangular mounting-frame ring and open-ended rectangular duct. Intentional removal of grille, small holes, crossbars, panels and corner detail; not a small-error or lossless substitute. Source placement/overall fitted dimensions retained. Original source, approved package and collision unchanged.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(dimensions,'triangles',len(t),flush=True)

if __name__=='__main__':main()
