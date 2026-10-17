#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Recheck actual contact payloads and source-qualified 17 mm opening paths."""
import argparse
import json
from pathlib import Path
from run import ROOT,module
import numpy as np
from cad_collision_profiles import native_loops
from cad_detail_passes import area
from mesh_quality import distances
from plan_cad_lods import digest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopoDS import TopoDS


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());detail=json.loads((out/'detail-summary.json').read_bytes());by={r['id']:r for r in summary['components']};native=module('source',ROOT/'benchmarks/2026-10-17-composed-pipeline/run.py').native
    # This module's sibling import is explicit; no environment path assumption.
    import sys
    sys.path.insert(0,str(ROOT/'benchmarks/2026-10-17-collision-solids'))
    check=module('contact_checks',ROOT/'benchmarks/2026-10-17-collision-solids/validate.py');panels=json.loads((ROOT/'out/rmuc2027-collision-solids/panels-summary.json').read_bytes());panel_by={r['id']:r for r in panels['components']};results=[]
    for row in detail['components']:
        cid=row['id'];path=ROOT/by[cid]['collision_glb'];mesh=np.load(path.with_suffix('.npz'));p,t,u=check.exported(path,mesh);records=[];skipped=0
        if cid.startswith('outpost/rotor/'):
            results.append({'id':cid,'exported_triangles':len(t),'qualified_opening_paths':[],'scope':'Exact exported geometry/owner payload only; no claimed native opening probes on this rotor.'});continue
        step=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step';doc,reader,faces,shells,owners=native(step);reference=np.load((ROOT/'out/rmuc2027-composed-pipeline'/cid/'candidate.glb').with_suffix('.npz'));selected=[]
        if cid in panel_by:
            for member in panel_by[cid]['members']:
                if member['accepted']:
                    selected.extend((v['front_native_face'],member['source_member'],v['depth_mm']+12) for v in member['panels'])
        else:
            for i in range(1,faces.Extent()+1):
                face=TopoDS.Face(faces.FindKey(i));surface=BRepAdaptor_Surface(face)
                if owners[i]==1 and surface.GetType()==GeomAbs_Plane and area(face)>=5000:selected.append((i,1,12))
        rays={};contacts={}
        for index,unit,back_length in selected:
            face=TopoDS.Face(faces.FindKey(index));n=np.array(BRepAdaptor_Surface(face).Plane().Axis().Direction().Coord());loops,_=native_loops(face,close_holes_below_mm=17)
            for loop in loops:
                if loop['outer']:continue
                center=loop['points_mm'].mean(0);start=center+n*12;end=center-n*back_length
                if unit not in rays:rays[unit]=check.source_raycaster(shells.FindKey(unit));contacts[unit]=check.raycaster(p,t[u==unit])
                old=reference['triangles'][reference['unit_ids']==unit]
                if rays[unit](start,end)is not None or distances(np.linspace(start,end,17),reference['positions_mm'],old).min()<8.5:skipped+=1;continue
                if contacts[unit](start,end)is not None:raise ValueError('source-qualified major opening filled '+cid+' '+str(index))
                clearance=float(distances(np.linspace(start,end,17),p,t[u==unit]).min())
                if clearance<8.495:raise ValueError('sampled 17 mm projectile clearance reduced '+cid+' '+str(index)+' '+str(clearance))
                records.append({'source_member':unit,'native_face_index':index,'start_mm':start.tolist(),'end_mm':end.tolist(),'minimum_candidate_surface_clearance_mm':clearance})
        results.append({'id':cid,'exported_triangles':len(t),'qualified_opening_paths':records,'skipped_native_occluded_or_non_projectile_clear_paths':skipped,'scope':'Exact export/owner payload and source-clear major hole centers qualified by 17 mm reference clearance. Center rays only; no swept-sphere or all-motion proof.'});print(cid,'opening rays',len(records),flush=True)
    report={'components':results,'summary_sha256':digest(out/'summary.json'),'producer_sha256':digest(__file__),'scope':'Independent actual-export equality and finite opening-center checks; not full trajectory/motion/clearance certification.'};(out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
