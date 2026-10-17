#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Generate independent original-source native mounting-removal previews."""
import argparse,gc,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_document import CadDocument
from cad_mounting_preview import bind_details,preview_mesh
from mesh_parts import tessellate
from validate_parts import read_part
from cad_wall_fill import shape_map
from plan_cad_lods import digest
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--id');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    audit_path=ROOT/'out/rmuc2027-mounting-details/audit-final.json';audit=json.loads(audit_path.read_bytes());inventory_path=ROOT/'out/rmuc2027-equipment-pipeline/inventory.json';inventory=json.loads(inventory_path.read_bytes());lookup={r['id']:r for r in inventory['components']};pipeline_path=ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py';spec=importlib.util.spec_from_file_location('pipeline',pipeline_path);pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline);results=[];helper=ROOT/'python/cad_mounting_preview.py'
    for component in audit['components']:
        cid=component['id']
        if a.id and cid!=a.id:continue
        folder=a.out/cid;folder.mkdir(parents=True,exist_ok=True);summary_path=folder/'summary.json'
        if summary_path.exists():
            prior=json.loads(summary_path.read_bytes())
            if prior['audit_sha256']!=digest(audit_path) or prior['producer_sha256']!=digest(Path(__file__)) or prior['preview_helper_sha256']!=digest(helper):raise ValueError('stale cached candidate')
            results.append(prior);continue
        source=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step'
        if digest(source)!=lookup[cid]['source_step_sha256']:raise ValueError('source work-part changed')
        all_holes=[r for r in audit['findings']['openings'] if cid in r['components']];holes=[r for r in all_holes if r['kind']=='circular-opening'];hardware=[r for r in audit['findings']['fasteners'] if cid in r['components']];native,reader,error=read_part(str(source))
        if error:raise ValueError(error)
        labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(native.Main()).GetFreeShapes(labels);root=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));faces=shape_map(root,TopAbs_FACE);owners=[];stats={}
        p,t,m,palette=tessellate(native,.4,.6,stats,lambda i,f,n:owners.extend([faces.FindIndex(f)]*n));owners=np.array(owners,int)
        if stats.get('unmeshed_faces') or faces.Extent()!=lookup[cid]['source_faces'] or len(owners)!=len(t):raise ValueError('source face accounting failed')
        with CadDocument.from_step(source,workers=1) as cad:bindings=bind_details(cad,root,holes,hardware);cad.verify_source()
        stages={}
        for stage,fill,remove in [('before',False,False),('holes',True,False),('fasteners',False,True),('combined',True,True)]:
            cp,ct,cm,cf,proof=preview_mesh(p,t,m,palette,owners,bindings,fill_holes=fill,remove_fasteners=remove);indices=np.array(proof['unchanged_input_triangle_indices'],int);retained_count=len(indices)
            if not np.array_equal(cp[ct[:retained_count]],p[t[indices]]) or not np.array_equal(cm[:retained_count],m[indices]):raise ValueError('untouched triangle or paint changed')
            pipeline.save_mesh(folder,stage,cp,ct,cm,palette,np.zeros(len(ct),int));np.save(folder/(stage+'-native-face-indices.npy'),cf)
            stages[stage]={'triangles':len(ct),'native_faces_retained':len(set(cf[cf>0])),'rebuilt_face_count':len(proof['rebuilt_faces']),'source_colours':palette,'proof':proof,'outputs_sha256':{name:digest(folder/name) for name in [stage+'.glb',stage+'.npz',stage+'-native-face-indices.npy']}}
        record={'id':cid,'audit_sha256':digest(audit_path),'source_step_sha256':digest(source),'source_faces':lookup[cid]['source_faces'],'uses':lookup[cid]['uses'],'opening_candidates':len(holes),'withheld_openings':len(all_holes)-len(holes),'fastener_candidates':len(hardware),'bindings':bindings['proof'],'stages':stages,'producer_sha256':digest(Path(__file__)),'preview_helper_sha256':digest(helper)};summary_path.write_text(json.dumps(record,indent=2)+'\n');results.append(record);print(cid,{s:r['triangles'] for s,r in stages.items()},'withheld hardware',len(bindings['proof']['withheld_source_fastener_unit_ids']),flush=True);del native,reader,root,faces,p,t,m,bindings;gc.collect()
    report={'components':results,'audit_sha256':digest(audit_path),'inventory_sha256':digest(inventory_path),'producer_sha256':{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),helper,ROOT/'python/mesh_parts.py']},'selection_policy':'Circular mouths under 17mm; all non-round openings withheld. Hardware requires equal source/native geometric multiplicity, otherwise withheld.','scope':'Original source native meshes, holes-only, fasteners-only, combined. Same .4mm/.6rad mesh request. Original face paint and untouched triangles retained exactly in memory. No edited STEP import, source mutation, collision/installed assets or delta to earlier optimized candidates.'};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
