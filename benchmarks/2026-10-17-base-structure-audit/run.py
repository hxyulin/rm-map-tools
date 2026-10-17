#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only source-feature and current-mesh cost audit for two Base members."""
import argparse,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_document import CadDocument
from p21split import Splitter
from plan_cad_lods import digest
from validate_parts import read_part
from cad_wall_fill import shape_map
from cad_detail_passes import small_bore_groups,area
from cad_surface_lods import wire_width_bound_mm
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID,TopAbs_WIRE,TopAbs_EDGE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.BRepTools import BRepTools
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.TopoDS import TopoDS
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

TARGETS={4268930:'Top crossbar',4527988:'Lower outer housing'}

def mesh_cost(d,i):
    mask=d['unit_ids']==i;p=d['positions_mm'];tri=d['triangles'][mask];colors=d['triangle_srgb'][mask];rows=[]
    palette,materials=np.unique(colors,axis=0,return_inverse=True)
    for k,col in enumerate(palette):
        tt=tri[materials==k];pp,inverse=np.unique(p[tt].reshape(-1,3),axis=0,return_inverse=True);t=inverse.reshape(-1,3)
        edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1);ee,counts=np.unique(edges,axis=0,return_counts=True)
        graph=coo_matrix((np.ones(len(ee)),(ee[:,0],ee[:,1])),shape=(len(pp),len(pp))).tocsr();n,labels=connected_components(graph,directed=False)
        normal=np.cross(pp[t[:,1]]-pp[t[:,0]],pp[t[:,2]]-pp[t[:,0]]);surfarea=np.linalg.norm(normal,axis=1)/2
        comp=[]
        for j in range(n):
            select=labels[t[:,0]]==j;vertices=pp[labels==j];comp.append({'triangles':int(select.sum()),'area_mm2':float(surfarea[select].sum()),'bbox_mm':[vertices.min(0).tolist(),vertices.max(0).tolist()]})
        rows.append({'srgb':col.tolist(),'triangles':len(t),'area_mm2':float(surfarea.sum()),'exact_position_connected_components':n,'boundary_edges':int((counts==1).sum()),'nonmanifold_edges':int((counts>2).sum()),'largest_components':sorted(comp,key=lambda x:x['triangles'],reverse=True)[:10]})
    return {'triangles':len(tri),'materials':sorted(rows,key=lambda x:x['triangles'],reverse=True)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--hierarchy',type=Path,default=ROOT/'out/rmuc2027-hierarchy');p.add_argument('--visual',type=Path,default=ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz');p.add_argument('--collision',type=Path,default=ROOT/'out/rmuc2027-base-gap-led-final/collision/geometry.npz');p.add_argument('--audit',type=Path,default=ROOT/'out/rmuc2027-base-light-final/source-audit.json');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);audit=json.loads(a.audit.read_bytes());source=a.out/'source.step';h=json.loads((a.hierarchy/'hierarchy.json').read_bytes());component=next(c for c in h['components'] if c['id']=='base/source-model')
    if not source.exists():
        with CadDocument.from_step(a.hierarchy/'field.step',workers=1,intern_layers=True,expected_sha256=h['files_sha256']['field.step']) as cad:
            splitter=Splitter(cad.index,cad.model);mask,rewrite=splitter.closure_products([cad.index.r(component['export_product_id'])]);splitter.write_closure(mask,rewrite,source);cad.verify_source()
    if digest(source)!=audit['component_step_sha256']:raise ValueError('source checksum mismatch')
    doc,reader,error=read_part(str(source))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);shape=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(shape,TopAbs_FACE);solids=shape_map(shape,TopAbs_SOLID);by_index={f['native_face_index']:f for f in audit['faces']}
    visual=np.load(a.visual);collision=np.load(a.collision);report={'source_component_sha256':digest(source),'current_visual_sha256':digest(a.visual),'current_collision_sha256':digest(a.collision),'units':[],'scope':'Read-only native source feature discovery and current candidate costs. Native face triangle counts are historical source tessellation, not current decimated ownership. Narrow planar loops may be markings, mounting slots or holes; width does not classify purpose or authorize deletion.'}
    for source_id,name in TARGETS.items():
        index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source_id);u=audit['units'][index];ids=set(u['face_ids']);native_indices={f['native_face_index'] for f in audit['faces'] if f['source_face_id'] in ids};body=None
        for j in range(1,solids.Extent()+1):
            s=solids.FindKey(j);ff=shape_map(s,TopAbs_FACE)
            if {faces.FindIndex(ff.FindKey(k)) for k in range(1,ff.Extent()+1)}==native_indices:body=s;break
        if body is None:raise ValueError('source unit binding missing')
        result={'source_unit_id':source_id,'name':name,'current_visual':mesh_cost(visual,index),'current_collision':mesh_cost(collision,index),'source_faces':len(ids),'source_surface_faces':dict(Counter(f['surface'] for f in audit['faces'] if f['source_face_id'] in ids)),'source_planar_faces':[]}
        groups=small_bore_groups(body,maximum_radius_mm=8.5,maximum_depth_mm=10000);result['complete_bores_below_17mm']=[g for g in groups if 2*g['radius_mm']<17-1e-6]
        for native_index in sorted(native_indices):
            f=by_index[native_index]
            if f['surface']!='Plane':continue
            face=TopoDS.Face(faces.FindKey(native_index));wires=shape_map(face,TopAbs_WIRE);outer=BRepTools.OuterWire_s(face);plane=BRepAdaptor_Surface(face).Plane();loops=[]
            for j in range(1,wires.Extent()+1):
                wire=TopoDS.Wire(wires.FindKey(j))
                if wire.IsSame(outer):continue
                loops.append({'native_wire_index':j,'width_upper_bound_mm':wire_width_bound_mm(face,wire),'edges':shape_map(wire,TopAbs_EDGE).Extent(),'area_mm2':area(BRepBuilderAPI_MakeFace(plane,wire,True).Face())})
            result['source_planar_faces'].append({**f,'normal':[plane.Axis().Direction().X(),plane.Axis().Direction().Y(),plane.Axis().Direction().Z()],'inner_loops':loops,'narrow_loop_count':sum(l['width_upper_bound_mm']<17 for l in loops),'outer_edges':shape_map(outer,TopAbs_EDGE).Extent()})
        result['source_planar_faces'].sort(key=lambda f:f['triangles'],reverse=True);report['units'].append(result);print(name,'visual',result['current_visual']['triangles'],'bores',len(result['complete_bores_below_17mm']),'loops',sum(len(f['inner_loops']) for f in result['source_planar_faces']),flush=True)
        report['producer_sha256']=digest(Path(__file__));(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
