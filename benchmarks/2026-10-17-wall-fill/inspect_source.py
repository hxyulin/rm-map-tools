#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Extract selected source bodies and inventory finite native wall geometry."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_document import CadDocument
from p21split import Splitter
from validate_parts import read_part
from mesh_parts import tessellate
from export_field_package import GlbWriter
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes())
    selected=['central-deck','central-tunnel-side/','central-tunnel-side-red/', 'under-highland-fan-grille','tunnel-fan-grille','red-trapezoid-highland','blue-trapezoid-highland']
    records=[]
    with CadDocument.from_step(ROOT/'out/rmuc2027-hierarchy/field.step',workers=1,intern_layers=True) as doc:
        if doc.source_sha256!=catalog['files_sha256']['field.step']:raise ValueError('source mismatch')
        splitter=Splitter(doc.index,doc.model)
        for c in catalog['components']:
            if not any(c['id'].startswith(p) for p in selected):continue
            name=c['id'].split('/')[0];folder=out/name;folder.mkdir()
            mask,rewrite=splitter.closure_products([doc.index.r(c['export_product_id'])]);splitter.write_closure(mask,rewrite,folder/'source.step')
            native,reader,error=read_part(str(folder/'source.step'))
            if error:raise ValueError(error)
            faces=[]
            def observe(i,f,n):
                box=Bnd_Box();BRepBndLib.AddOptimal_s(f,box,False,False)
                props=GProp_GProps();BRepGProp.SurfaceProperties_s(f,props)
                surf=BRepAdaptor_Surface(f);kind=str(surf.GetType()).rsplit('_',1)[-1]
                record={'native_face_index':i,'triangles':n,'kind':kind,'area_mm2':props.Mass(),'bbox_mm':[v for p in (box.CornerMin(),box.CornerMax()) for v in (p.X(),p.Y(),p.Z())]}
                if kind=='Plane':
                    normal=surf.Plane().Axis().Direction();record['normal']=[normal.X(),normal.Y(),normal.Z()]
                faces.append(record)
            stats={};p,t,ci,colors=tessellate(native,.4,.25,stats,observe)
            if stats.get('unmeshed_faces') or len(faces)!=c['face_count']:raise ValueError('mesh mismatch')
            w=GlbWriter(name,{'version':'2.0','copyright':'DJI / RoboMaster source geometry'})
            w.add_node(name,p/1000,t,[colors[int(i)] for i in ci]);w.write(folder/'source.glb')
            record={'component':c,'source_sha256':doc.source_sha256,'triangles':len(t),'faces':faces,'colours':colors}
            (folder/'audit.json').write_text(json.dumps(record,indent=2)+'\n');records.append({'component_id':c['id'],'triangles':len(t)})
            print(name,len(t),flush=True)
        doc.verify_source()
    (out/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
if __name__=='__main__':main()
