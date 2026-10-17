#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Extend guarded source-outline detail LOD across heavy Base members, preserving lights."""
import argparse,json,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from scipy.spatial import cKDTree
from cad_local_lod import planar_outline_vertices,guarded_vertex_lod
from cad_wall_fill import shape_map
from validate_parts import read_part
from plan_cad_lods import digest
from export_field_package import GlbWriter
from mesh_quality import deviation
from OCP.TopAbs import TopAbs_FACE,TopAbs_SOLID,TopAbs_SHELL
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def lights(c):return ((c[:,0]>.9)&(c[:,1]<.1))|((c[:,1]>.1)&(c[:,1]>.9)&(c[:,0]<.1))


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    source=ROOT/'out/rmuc2027-base-structure-audit/source.step';audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());reference=ROOT/'out/rmuc2027-base-surface-lods-v3/approved/geometry.npz';current_path=ROOT/'out/rmuc2027-base-light-final/ico2/geometry.npz';native=np.load(reference);current=np.load(current_path);source_summary=json.loads((ROOT/'out/rmuc2027-base-housing-local-final/summary.json').read_bytes())
    if digest(source)!=audit['component_step_sha256'] or digest(reference)!=source_summary['source_geometry_sha256'] or digest(current_path)!=source_summary['reference_geometry_sha256']:raise ValueError('approved input mismatch')
    doc,reader,error=read_part(str(source))
    if error:raise ValueError(error)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);lookup={}
    for kind in (TopAbs_SOLID,TopAbs_SHELL):
        shapes=shape_map(root,kind)
        for j in range(1,shapes.Extent()+1):
            shape=shapes.FindKey(j);ff=shape_map(shape,TopAbs_FACE);lookup[(kind,frozenset(faces.FindIndex(ff.FindKey(k)) for k in range(1,ff.Extent()+1)))]=shape
    selected=[u['source_id'] for i,u in enumerate(audit['units']) if int((current['unit_ids']==i).sum())>=2000 and u['source_id'] not in (4268930,4527988)];a.out.mkdir(parents=True);report={'component_step_sha256':digest(source),'source_geometry_sha256':digest(reference),'current_geometry_sha256':digest(current_path),'selected_source_units':selected,'decisions':[],'scope':'1 mm nominal / 3 mm sampled source-detail LOD on selected heavy Base bodies. Approved light triangle positions/colours remain exact; crossbar and small source members unchanged. Native source, collision, detectors and installed assets unchanged.'}
    def save():
        report['producer_sha256']={str(path.relative_to(ROOT)):digest(path) for path in [Path(__file__),ROOT/'python/cad_local_lod.py',ROOT/'python/simplify_package.py']};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    for source_id in selected:
        index=next(i for i,u in enumerate(audit['units']) if u['source_id']==source_id);u=audit['units'][index];mask=(native['unit_ids']==index)&~lights(native['triangle_srgb']);used,inv=np.unique(native['triangles'][mask],return_inverse=True);p=native['positions_mm'][used];t=inv.reshape(-1,3);palette,m=np.unique(native['triangle_srgb'][mask],axis=0,return_inverse=True);indices={f['native_face_index'] for f in audit['faces'] if f['unit']==index};shape=lookup[(TopAbs_SOLID if u['kind']=='solid' else TopAbs_SHELL,frozenset(indices))];outline,selection=planar_outline_vertices(shape,minimum_face_area_mm2=20000,corner_turn_rad=math.radians(15));tree=cKDTree(p);protected=set();matched=0;missing=0
        if len(outline):
            dist,near=tree.query(outline);protected.update(map(int,near[dist<=.01]));matched=int((dist<=.01).sum());missing=int((dist>.01).sum())
            for k in np.flatnonzero(dist>.01):protected.update(map(int,np.asarray(tree.query(outline[k],k=min(8,len(p)))[1]).ravel()))
        try:
            pp,tt,mm,proof=guarded_vertex_lod(p,t,m,error_mm=1,sampled_limit_mm=3,sample_count=262144,maximum_iterations=16,protected_vertex_indices=np.asarray(sorted(protected),dtype=np.int64));sampled=deviation(p,t,pp,tt,count=16384)
            if sampled['max']>3:raise ValueError('combined sampled guard failed')
            oldmask=current['unit_ids']==index;ledmask=oldmask&lights(current['triangle_srgb']);old_light=current['positions_mm'][current['triangles'][ledmask]];points=[pp,old_light.reshape(-1,3)];triangles=[tt,np.arange(len(old_light)*3).reshape(-1,3)+len(pp)];colors=[palette[mm],current['triangle_srgb'][ledmask]];pp=np.concatenate(points);tt=np.concatenate(triangles);cc=np.concatenate(colors)
            if len(tt)>=int(oldmask.sum()):raise ValueError('candidate does not save triangles')
            if not np.array_equal(pp[tt[lights(cc)]],old_light) or not np.array_equal(cc[lights(cc)],current['triangle_srgb'][ledmask]):raise ValueError('approved light positions/colours changed')
            folder=a.out/str(source_id);folder.mkdir();np.savez(folder/'geometry.npz',positions_mm=pp,triangles=tt,triangle_srgb=cc,unit_ids=np.full(len(tt),index,dtype=np.uint32),source_face_ids=np.zeros(len(tt),dtype=np.uint32));w=GlbWriter('base/member-aggressive',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; derived outline-protected body LOD, approved lights retained'});w.add_node('source-unit-'+str(source_id),pp/1000,tt,[','.join(map(str,c)) for c in cc],extras={'source_unit_id':source_id,'inspection_only':True});w.write(folder/'visual.glb')
            decision={'source_unit_id':source_id,'accepted':True,'before_triangles':int(oldmask.sum()),'after_triangles':len(tt),'protected_light_triangles':len(old_light),'direct_outline_matches':matched,'outline_neighbor_fallbacks':missing,'outline_protected_vertices':sorted(protected),'outline_selection':selection,'lod':proof,'native_reference_sampled_deviation_mm':sampled,'geometry_sha256':digest(folder/'geometry.npz'),'visual_sha256':digest(folder/'visual.glb')};print(source_id,int(oldmask.sum()),'->',len(tt),flush=True)
        except ValueError as e:decision={'source_unit_id':source_id,'accepted':False,'reason':str(e)};print(source_id,'retained',str(e),flush=True)
        report['decisions'].append(decision);save()
if __name__=='__main__':main()
