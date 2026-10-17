#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Measure residual shell costs in the composed Rune, Resource and Tech Core meshes."""
import argparse, importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from plan_cad_lods import digest
from cad_wall_fill import shape_map
from cad_detail_passes import area
from OCP.TopAbs import TopAbs_FACE,TopAbs_SHELL,TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane

TARGETS=['rune/banks/bank-a/hub-cluster','rune/banks/bank-b/hub-cluster','rune/support-and-shared','resource-area/mechanism','technology-core/tool-head']

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    composed=ROOT/'out/rmuc2027-composed-pipeline'; manifest=json.loads((composed/'summary.json').read_bytes());lookup={c['id']:c for c in manifest['components']};loader=module('composition',ROOT/'benchmarks/2026-10-17-composed-pipeline/run.py');results=[]
    for cid in TARGETS:
        r=lookup[cid];meshpath=composed/cid/'candidate.npz';glb=ROOT/r['candidate_glb'];step=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step'
        if digest(glb)!=r['candidate_sha256'] or digest(step)!=r['source_step_sha256']:raise ValueError('pinned source/candidate changed')
        mesh=np.load(meshpath);p=mesh['positions_mm'];t=mesh['triangles'];m=mesh['material_ids'];u=mesh['unit_ids'];pal=[c or None for c in mesh['palette'].tolist()]
        doc,reader,faces,shells,owner=loader.native(step);units=[];native_faces=[]
        for i in range(1,faces.Extent()+1):
            f=TopoDS.Face(faces.FindKey(i));surface=BRepAdaptor_Surface(f);kind=str(surface.GetType()).split('_')[-1];record={'native_face_index':i,'native_shell_index':owner[i],'kind':kind,'area_mm2':area(f)}
            if kind=='Plane':
                plane=surface.Plane();d=np.array(plane.Axis().Direction().Coord())*(-1 if f.Orientation()==TopAbs_REVERSED else 1);record.update(normal=d.tolist(),offset_mm=float(np.array(plane.Location().Coord())@d))
            native_faces.append(record)
        for unit in np.unique(u):
            ids=u==unit;g=p[t[ids]];local=[f for f in native_faces if f['native_shell_index']==unit]
            units.append({'unit':int(unit),'triangles':int(ids.sum()),'bbox_mm':[g.min((0,1)).tolist(),g.max((0,1)).tolist()],'span_mm':np.ptp(g,axis=(0,1)).tolist(),'materials':{str(pal[int(k)]):int((m[ids]==k).sum()) for k in np.unique(m[ids])},'native_face_count':len(local),'native_planar_area_mm2':sum(f['area_mm2'] for f in local if f['kind']=='Plane'),'largest_native_planes':sorted([f for f in local if f['kind']=='Plane'],key=lambda f:f['area_mm2'],reverse=True)[:6]})
        report={'id':cid,'uses':r['uses'],'triangles':len(t),'source_step_sha256':digest(step),'reference_npz_sha256':digest(meshpath),'reference_glb_sha256':digest(glb),'units':sorted(units,key=lambda v:v['triangles'],reverse=True)};results.append(report);print(cid,len(t),'TOP',[(v['unit'],v['triangles'],np.round(v['span_mm'],1).tolist(),v['materials']) for v in report['units'][:8]],flush=True)
    result={'components':results,'composed_summary_sha256':digest(composed/'summary.json'),'producer_sha256':digest(Path(__file__))};(a.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
