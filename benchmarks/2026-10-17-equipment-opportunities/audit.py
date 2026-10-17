#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Read-only cost/primitive audit and native retessellation diagnostics.

Source CAD/appearance belongs to DJI / RoboMaster. Source, installed assets and
approved candidates stay unchanged; trial meshes are ignored inspection output.
"""
import argparse,collections,gc,importlib.util,json,math,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_detail_passes import area,small_bore_groups
from cad_wall_fill import shape_map
from mesh_parts import tessellate
from mesh_quality import deviation
from plan_cad_lods import digest
from validate_parts import read_part
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.TopAbs import TopAbs_FACE,TopAbs_SHELL
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label

GROUPS={'energy-unit':'Energy Units','fan':'Fans','rune':'Rune','resource-area':'Resource mechanisms','technology-core':'Tech Core tool heads'}

def selected(cid):
    return cid.startswith('rune/') or cid in ['energy-unit/unit','fan/body-2717086','resource-area/mechanism','technology-core/tool-head']

def histogram(values):
    return {str(k):{'faces':sum(r['area_mm2']<k for r in values),'native_triangles':sum(r['native_triangles'] for r in values if r['area_mm2']<k)} for k in [1,5,25,100]}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);source=ROOT/'out/rmuc2027-equipment-pipeline';hp=ROOT/'out/rmuc2027-hierarchy/hierarchy.json';hierarchy=json.loads(hp.read_bytes());ledger=json.loads((source/'passes.json').read_bytes());lookup={c['id']:c for c in hierarchy['components']};results=[];start=time.perf_counter()
    spec=importlib.util.spec_from_file_location('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
    for prior in ledger['components']:
        cid=prior['id']
        if not selected(cid):continue
        folder=source/cid;target=a.out/cid;target.mkdir(parents=True,exist_ok=True)
        if digest(folder/'source.step')!=prior['source_step_sha256'] or digest(folder/'native.npz')!=prior['native_npz_sha256'] or digest(folder/'lod.glb')!=prior['outputs_sha256']['lod.glb']:raise ValueError('approved source/reference changed')
        native=np.load(folder/'native.npz');current=np.load(folder/'lod.npz');doc,reader,error=read_part(str(folder/'source.step'))
        if error:raise ValueError(error)
        roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);root=XCAFDoc_ShapeTool.GetShape_s(roots.Value(1));faces=shape_map(root,TopAbs_FACE);shells=shape_map(root,TopAbs_SHELL);owner={};shell_shapes={}
        for j in range(1,shells.Extent()+1):
            shape=shells.FindKey(j);local=shape_map(shape,TopAbs_FACE);shell_shapes[j]=shape
            for k in range(1,local.Extent()+1):
                fi=faces.FindIndex(local.FindKey(k))
                if fi in owner:raise ValueError('ambiguous native shell ownership')
                owner[fi]=j
        records=[];triangle_units=[];stats={}
        def observe(index,face,count):
            surface=BRepAdaptor_Surface(face);kind=str(surface.GetType()).split('_')[-1];unit=owner.get(faces.FindIndex(face),-index);triangle_units.extend([unit]*count);r={'native_face_index':index,'native_shell_index':unit,'surface':kind,'native_triangles':count,'area_mm2':area(face)}
            if kind=='Cylinder':
                cylinder=surface.Cylinder();axis=cylinder.Axis();direction=np.array([axis.Direction().X(),axis.Direction().Y(),axis.Direction().Z()]);origin=np.array([axis.Location().X(),axis.Location().Y(),axis.Location().Z()]);direction*=1 if direction[np.argmax(abs(direction))]>=0 else -1;anchor=origin-direction*(origin@direction);r['radius_mm']=cylinder.Radius();r['axis_direction']=direction.tolist();r['axis_anchor_mm']=anchor.tolist();uv=BRepTools.UVBounds_s(face);r['u_span_rad']=uv[1]-uv[0];r['axial_span_mm']=abs(uv[3]-uv[2]);r['support_key']=list(np.round(np.r_[anchor,cylinder.Radius(),direction],6))
            records.append(r)
        p,t,m,palette=tessellate(doc,.4,.25,stats,observe)
        if len(t)!=prior['native_triangles'] or len(records)!=prior['source_faces'] or len(triangle_units)!=len(t) or stats.get('unmeshed_faces'):raise ValueError('native inventory mismatch')
        offset=0;surface_cost=collections.Counter();support_groups=collections.defaultdict(list)
        for r in records:
            keys={palette[int(i)] for i in m[offset:offset+r['native_triangles']]};r['source_colour']=next(iter(keys)) if len(keys)==1 else None;offset+=r['native_triangles'];surface_cost[r['surface']]+=r['native_triangles']
            if 'support_key' in r:support_groups[tuple(r['support_key'])].append(r)
        shell_records=[];native_units=np.array(triangle_units);current_u=current['unit_ids'];current_m=current['material_ids'];current_palette=[s or None for s in current['palette'].tolist()]
        for unit in np.unique(current_u):
            ids=current_u==unit;tri=current['triangles'][ids];xyz=current['positions_mm'][tri];span=np.ptp(xyz,axis=(0,1));colours=collections.Counter(current_palette[int(k)] for k in current_m[ids]);local_faces=[r for r in records if r['native_shell_index']==unit];bores=[]
            if unit>0 and len(local_faces)>=6:bores=small_bore_groups(shell_shapes[int(unit)],maximum_radius_mm=8.499,maximum_depth_mm=25)
            shell_records.append({'native_shell_index':int(unit),'current_triangles':len(tri),'native_triangles':int((native_units==unit).sum()),'native_faces':len(local_faces),'span_mm':span.tolist(),'bbox_mm':[xyz.min((0,1)).tolist(),xyz.max((0,1)).tolist()],'triangles_by_colour':{k or 'unresolved':v for k,v in colours.items()},'small_bore_count':len(bores),'small_bore_cylinder_faces':sum(len(g['face_indices']) for g in bores)})
        by_material=[]
        for i,colour in enumerate(current_palette):
            count=int((current_m==i).sum());protected=colour is None or np.ptp(list(map(float,colour.split(','))))>.1
            by_material.append({'source_colour':colour,'current_triangles':count,'frozen_by_generic_colour_policy':bool(protected),'reason':'unresolved source appearance' if colour is None else 'RGB range exceeds conservative 0.1 threshold' if protected else 'neutral region eligible for generic LOD'})
        native_colours=[r['source_colour'] for r in records];coarse_records=[];coarse_stats={};cp,ct,cm,cpl=tessellate(doc,.4,.6,coarse_stats,lambda i,f,n:coarse_records.append((i,n)))
        if len(coarse_records)!=len(records) or coarse_stats.get('unmeshed_faces'):raise ValueError('coarse native meshing lost faces')
        off=0
        for (index,count),r in zip(coarse_records,records):
            if index!=r['native_face_index'] or not count:raise ValueError('coarse native face accounting changed')
            keys={cpl[int(k)] for k in cm[off:off+count]}
            if keys!={r['source_colour']}:raise ValueError('coarse native face colour changed')
            off+=count
        quality=deviation(native['positions_mm'],native['triangles'],cp,ct,count=8192);pipeline.save_mesh(target,'native-angular-trial',cp,ct,cm,cpl,np.concatenate([np.full(n,owner.get(i,-i),int) for i,n in coarse_records]))
        groups=[]
        for rs in support_groups.values():groups.append({'faces':len(rs),'native_triangles':sum(r['native_triangles'] for r in rs),'radius_mm':rs[0]['radius_mm'],'axis_direction':rs[0]['axis_direction'],'axis_anchor_mm':rs[0]['axis_anchor_mm'],'total_trimmed_u_span_rad':sum(r['u_span_rad'] for r in rs),'native_face_indices':[r['native_face_index'] for r in rs]})
        result={'id':cid,'group':GROUPS[cid.split('/')[0]],'source_product_id':prior['source_product_id'],'uses':prior['uses'],'source_step_sha256':prior['source_step_sha256'],'approved_glb_sha256':prior['outputs_sha256']['lod.glb'],'approved_npz_sha256':digest(folder/'lod.npz'),'source_units':lookup[cid]['unit_count'],'native_import_shells':shells.Extent(),'native_faces':len(records),'native_triangles':len(native['triangles']),'current_triangles':len(current['triangles']),'current_materials':by_material,'native_triangles_by_surface':dict(surface_cost),'native_small_faces':histogram(records),'current_small_units':{str(k):{'units':sum(max(s['span_mm'])<=k for s in shell_records),'triangles':sum(s['current_triangles'] for s in shell_records if max(s['span_mm'])<=k)} for k in [10,17,30,50]},'current_units_under_128_triangles':{'units':sum(s['current_triangles']<128 for s in shell_records),'triangles':sum(s['current_triangles'] for s in shell_records if s['current_triangles']<128)},'small_bore_candidates':sum(s['small_bore_count'] for s in shell_records),'top_current_shells':sorted(shell_records,key=lambda s:s['current_triangles'],reverse=True)[:15],'top_native_faces':sorted(records,key=lambda s:s['native_triangles'],reverse=True)[:15],'top_cylinder_support_candidates':sorted(groups,key=lambda s:s['native_triangles'],reverse=True)[:15],'native_angular_trial':{'linear_deflection_mm':.4,'angular_deflection_rad':.6,'triangles':len(ct),'delta_from_current':len(current['triangles'])-len(ct),'source_faces_retained':len(coarse_records),'source_face_colours_retained':True,'sampled_native_deviation_mm':quality,'visual_sha256':digest(target/'native-angular-trial.glb'),'stats':coarse_stats,'scope':'Diagnostic source retessellation only; all CAD faces and per-face colour bindings retained, but triangle positions, normals and light/paint boundaries are not bit-exact; not an approved replacement.'}}
        (target/'audit.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result);print(cid,len(current['triangles']),'angular trial',len(ct),'frozen',sum(r['current_triangles'] for r in by_material if r['frozen_by_generic_colour_policy']),'bores',result['small_bore_candidates'],flush=True);del doc,reader,root,faces,shells,p,t,m,cp,ct,cm;gc.collect()
    report={'components':results,'elapsed_seconds':time.perf_counter()-start,'source_ledger_sha256':digest(source/'passes.json'),'hierarchy_sha256':digest(hp),'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/mesh_parts.py',ROOT/'python/cad_detail_passes.py']},'scope':'Read-only audit of approved visual geometry and original source CAD. Native surface/face costs are not residual LOD costs. Shell size, colour, bore discovery and rounded support clusters do not establish removability or finite-patch equivalence. Diagnostic coarse retessellation is not installed or approved.'};(a.out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
