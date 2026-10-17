#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Check source binding, shell retention, source error guards and byte-exact exports."""
import argparse,json,tempfile
from pathlib import Path
from audit import ROOT,module
import numpy as np
from plan_cad_lods import digest
from gltf_scene import read_glb,write_glb


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=a.out.resolve();summary=json.loads((out/'summary.json').read_bytes());skin=json.loads((out/'skin-summary.json').read_bytes());audit=json.loads((out/'audit.json').read_bytes());lookup={r['id']:r for r in skin['components']};pipeline=module('pipeline',ROOT/'benchmarks/2026-10-17-equipment-pipeline/run.py');checks=[]
    if digest(out/'summary.json')!=skin['reference_summary_sha256'] or digest(out/'audit.json')!=summary['audit_sha256'] or digest(ROOT/'out/rmuc2027-composed-pipeline/summary.json')!=audit['composed_summary_sha256']:raise ValueError('residual lineage changed')
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory)
        for row in summary['components']:
            cid=row['id'];source=ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step'
            if digest(source)!=row['source_step_sha256']:raise ValueError('source STEP changed')
            native=ROOT/'out/rmuc2027-mounting-native'/cid;native_report=json.loads((native/'summary.json').read_bytes())
            if native_report['source_step_sha256']!=row['source_step_sha256']:raise ValueError('edited native identity mismatch')
            for name,key in [('combined.npz','native_edited_npz_sha256'),('combined-native-face-indices.npy','native_edited_face_ledger_sha256')]:
                if digest(native/name)!=row[key] or digest(native/name)!=native_report['stages']['combined']['outputs_sha256'][name]:raise ValueError('edited source binding changed')
            reference=ROOT/'out/rmuc2027-composed-pipeline'/cid/'candidate.npz'
            if digest(reference)!=row['reference_npz_sha256']:raise ValueError('residual baseline changed')
            for path,sha in row['producer_sha256'].items():
                if digest(ROOT/path)!=sha:raise ValueError('residual producer changed')
            for unit in row['units']:
                guard=unit.get('source_detail')
                if guard and guard['sampled_deviation_mm']['max']>guard['sampled_limit_mm']+.001:raise ValueError('source LOD guard failed')
            for unit in lookup[cid]['units']:
                guard=unit.get('skin')
                if guard and guard['accepted'] and (guard['maximum_foreground_difference']>.0002 or guard['maximum_rgb_changed_over_10_fraction']>.001):raise ValueError('skin admission guard failed')
            for stage in ['planar','detail','skin']:
                npz=out/cid/(stage+'.npz');glb=out/cid/(stage+'.glb');expected=(lookup[cid] if stage=='skin' else row)['outputs_sha256']
                if digest(npz)!=expected[stage+'.npz'] or digest(glb)!=expected[stage+'.glb']:raise ValueError('residual output changed')
                mesh=np.load(npz);pipeline.save_mesh(tmp,stage,mesh['positions_mm'],mesh['triangles'],mesh['material_ids'],[v or None for v in mesh['palette'].tolist()],mesh['unit_ids'])
                if digest(tmp/(stage+'.glb'))!=digest(glb):raise ValueError('actual GLB differs from payload')
            checks.append({'id':cid,'source_and_native_ledger_verified':True,'exact_full_glb_reexports':3})
        for path,sha in skin['producer_sha256'].items():
            if digest(ROOT/path)!=sha:raise ValueError('skin producer changed')
    final=json.loads((out/'final-summary.json').read_bytes())
    if final['skin_summary_sha256']!=digest(out/'skin-summary.json'):raise ValueError('final lineage mismatch')
    profile_path=out/'technology-core/tool-head/profile.json';profile=json.loads(profile_path.read_bytes())
    for name,sha in profile['producer_sha256'].items():
        if digest(ROOT/name)!=sha:raise ValueError('profile producer changed')
    if not profile['valid_solid'] or abs(profile['depth_mm']-8)>.00001 or profile['projection_union']['maximum_lateral_shift_mm']>.001:raise ValueError('profile envelope policy failed')
    with tempfile.TemporaryDirectory() as directory:
        tmp=Path(directory)
        for row in final['components']:
            cid=row['id'];stage=row['selected_stage'];mesh=np.load(out/cid/'final.npz')
            selected=profile if stage=='profile' else lookup[cid]
            for suffix in ['.npz','.glb']:
                expected=selected['outputs_sha256'][stage+suffix]
                if digest(out/cid/('final'+suffix))!=expected or row['outputs_sha256']['final'+suffix]!=expected:raise ValueError('final selection mismatch')
            pipeline.save_mesh(tmp,stage,mesh['positions_mm'],mesh['triangles'],mesh['material_ids'],[v or None for v in mesh['palette'].tolist()],mesh['unit_ids'])
            if stage=='profile':
                doc,blob=read_glb(tmp/(stage+'.glb'))
                for node in doc['nodes']:
                    if node.get('extras',{}).get('native_shell_index')==4:node['extras'].update(derived_geometry=True,source_native_shell_binding=4,geometry_role='native-projected-profile-prism',native_geometry_identity_claim=False)
                write_glb(tmp/(stage+'.glb'),doc,blob)
                points=mesh['positions_mm'][mesh['triangles'][mesh['unit_ids']==4]]
                projected=points@np.array(profile['normal']);offset=profile['projection_union']['front_offset_mm']
                if projected.max()>offset+.001 or projected.min()<offset-8-.001:raise ValueError('exported plate outside source depth')
            if digest(tmp/(stage+'.glb'))!=digest(out/cid/'final.glb'):raise ValueError('final actual GLB differs from payload')
        result={'components':checks,'full_glb_reexports':sum(c['exact_full_glb_reexports'] for c in checks)+len(final['components']),'final_summary_sha256':digest(out/'final-summary.json'),'profile_proof_sha256':digest(profile_path),'summary_sha256':digest(out/'summary.json'),'skin_summary_sha256':digest(out/'skin-summary.json'),'producer_sha256':digest(Path(__file__))};(out/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print('Validated all five source definitions and 20 byte-exact GLB reexports')
if __name__=='__main__':main()
