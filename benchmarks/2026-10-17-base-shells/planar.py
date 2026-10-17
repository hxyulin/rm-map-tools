#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Try boundary-defined planar skins on explicitly selected Base members."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
import numpy as np
from cad_planar_shell import planar_skin
from plan_cad_lods import digest
from export_field_package import GlbWriter

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);source=ROOT/'out/rmuc2027-base-shells-audit/baseline.npz';d=np.load(source);audit=json.loads((ROOT/'out/rmuc2027-base-light-final/source-audit.json').read_bytes());report={'input_sha256':digest(source),'units':[]}
    for source_id in [4268930,4527988,4314593,4353403,4392221,4594338,4664029,4693907,4723785,4756187,4764759]:
        i=next(i for i,u in enumerate(audit['units']) if u['source_id']==source_id);mask=d['unit_ids']==i;used,inv=np.unique(d['triangles'][mask],return_inverse=True);p=d['positions_mm'][used];t=inv.reshape(-1,3);palette,m=np.unique(d['triangle_srgb'][mask],axis=0,return_inverse=True);protected=[j for j,c in enumerate(palette) if c[0]>.9 and c[1]<.1 or c[1]>.9 and c[0]<.1];pp,tt,mm,proof=planar_skin(p,t,m,protected_material_ids=protected);folder=a.out/str(source_id);folder.mkdir(exist_ok=True);np.savez(folder/'geometry.npz',positions_mm=pp,triangles=tt,triangle_srgb=palette[mm],unit_ids=np.full(len(tt),i,dtype=np.uint32),source_face_ids=np.zeros(len(tt),dtype=np.uint32));w=GlbWriter('base/planar-skin',{'version':'2.0','copyright':'DJI / RoboMaster source geometry; boundary-defined planar skin'});w.add_node('source-unit-'+str(source_id),pp/1000,tt,[','.join(map(str,c)) for c in palette[mm]],extras={'source_unit_id':source_id,'inspection_only':True});w.write(folder/'visual.glb');report['units'].append({'source_unit_id':source_id,'before_triangles':len(t),'after_triangles':len(tt),'skin':proof});print(source_id,len(t),'->',len(tt),flush=True)
    report['producer_sha256']={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/'python/cad_planar_shell.py']};(a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
