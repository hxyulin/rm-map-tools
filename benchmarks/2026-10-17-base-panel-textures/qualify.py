#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check panel-difference samples against the explicit finite native edit volume."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from mesh_quality import sample_points,distances
from cad_surface_lods import profile_prism
from cad_wall_fill import shape_map
from validate_parts import read_part
from OCP.TopAbs import TopAbs_FACE,TopAbs_IN,TopAbs_ON
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.gp import gp_Pnt
from plan_cad_lods import digest


def main():
    old=np.load(ROOT/'out/rmuc2027-base-crossbar-skin/geometry.npz');new=np.load(ROOT/'out/rmuc2027-base-panel-trials/4202749/optimized.npz');a=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());doc,r,e=read_part(str(ROOT/'out/rmuc2027-base-structure-audit/source.step'))
    if e:raise ValueError(e)
    roots=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(roots);faces=shape_map(XCAFDoc_ShapeTool.GetShape_s(roots.Value(1)),TopAbs_FACE);face=faces.FindKey(next(f['native_face_index'] for f in a['faces'] if f['source_face_id']==4202749));solid,proof=profile_prism(face,depth_mm=-6,maximum_gap_mm=17);classifier=BRepClass3d_SolidClassifier(solid);rows=[]
    for name,left,right in [('reference-to-candidate',old,new),('candidate-to-reference',new,old)]:
        samples=sample_points(left['positions_mm'],left['triangles'],16384);values=distances(samples,right['positions_mm'],right['triangles']);bad=values>3.001;outside=[]
        for sample,value in zip(samples[bad],values[bad]):
            point=gp_Pnt(*map(float,sample));classifier.Perform(point,1e-6)
            if classifier.State() in [TopAbs_IN,TopAbs_ON]:continue
            measure=BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(point).Vertex(),solid);measure.Perform()
            if not measure.IsDone() or measure.Value()>3.001:outside.append({'point_mm':sample.tolist(),'surface_distance_mm':float(value),'edit_volume_distance_mm':float(measure.Value()) if measure.IsDone() else None})
        rows.append({'direction':name,'sample_count':len(samples),'maximum_mm':float(values.max()),'over_3_001_mm_samples':int(bad.sum()),'outside_edit_volume_plus_lod_margin':outside})
    report={'reference_sha256':digest(ROOT/'out/rmuc2027-base-crossbar-skin/geometry.npz'),'candidate_sha256':digest(ROOT/'out/rmuc2027-base-panel-trials/4202749/optimized.npz'),'checks':rows,'accepted':not any(r['outside_edit_volume_plus_lod_margin'] for r in rows),'scope':'Finite samples against the prior crossbar; differences above 3.001 mm must be in/within 3.001 mm of the native replacement solid. Not a continuous surface certificate.','producer_sha256':digest(Path(__file__))};out=ROOT/'out/rmuc2027-base-panel-trials/4202749/qualification.json';out.write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
