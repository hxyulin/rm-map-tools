#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Package references; validate GLB counts/colors and expose placement/membership."""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from gltf_scene import read_glb,write_glb,mesh_instances
from cad_glb_composition import RigidComposer
from plan_cad_lods import digest
OUT=ROOT/'out/rmuc2027-protected-source-reference';BENCH=Path(__file__).resolve().parent

def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def main():
    ledger=json.loads((OUT/'ledger.json').read_bytes());verified=[];membership=[]
    front_path=ROOT/'out/rmuc2027-rune-front/summary.json';rear_path=ROOT/'out/rmuc2027-rune-flat-back/summary.json'
    fronts={c['id']:c for c in json.loads(front_path.read_bytes())['components']}
    rears={c['id']:c for c in json.loads(rear_path.read_bytes())['components']}
    for r in ledger['references']:
        path=ROOT/r['reference_glb'];d,b=read_glb(path);data=np.load(path.with_suffix('.npz'))
        count=sum(len(t) for _,_,p,t,m in mesh_instances(d,b));assert count==r['triangles']
        colors={tuple(m['extras']['step_colour_srgb']) if m['extras']['step_colour_srgb'] is not None else None for m in d['materials']}
        source_colors={tuple(map(float,k.split(','))) if k else None for k in r['palette']}
        assert colors<=source_colors
        verified.append({'id':r['id'],'glb_triangles_verified':count,'source_material_metadata_verified':True})
        cache=ROOT/'out/rmuc2027-equipment-pipeline'/r['component_id']/'native.npz';native_to_source={}
        if cache.exists():
            c=np.load(cache);assert len(c['unit_ids'])==len(data['source_unit_ids'])
            for native in np.unique(c['unit_ids']):
                source=np.unique(data['source_unit_ids'][c['unit_ids']==native]);assert len(source)==1
                native_to_source[int(native)]=int(source[0])
        mesh_map=[]
        for n in r['runtime']['mesh_nodes']:
            e=n['extras'];original=e.get('source_unit_id',e.get('rm',{}).get('source_id'))
            native=e.get('source_native_shell_index',e.get('source_native_shell_binding'))
            if original is None and native is not None:original=native_to_source.get(native)
            derived_proof=None;source_ids=[original] if original is not None else []
            if native is not None and native<0 and r['component_id'] in fronts:
                if native==-1:
                    derived_proof={'file':str(rear_path.relative_to(ROOT)),'sha256':digest(rear_path),'profiles':rears[r['component_id']]['flat_back']['source_profiles']}
                    source_ids=sorted({native_to_source[v['native_shell_index']] for v in derived_proof['profiles']})
                else:
                    proof=next(v for v in fronts[r['component_id']]['derived_fronts'] if v['unit_id']==native)
                    derived_proof={'file':str(front_path.relative_to(ROOT)),'sha256':digest(front_path),'source_native_shell_index':proof['source_native_shell_index'],'shell_local_face_indices':proof['shell_local_face_indices']}
                    source_ids=[native_to_source[proof['source_native_shell_index']]]
            mesh_map.append({'runtime_node_index':n['index'],'runtime_node_name':n['name'],'source_unit_id':original,'source_unit_ids':source_ids,'derived_profile_provenance':derived_proof,'native_shell_index':native,'source_unit_kind':r['source_units'].get(str(original)),'mapping_complete':bool(source_ids)})
        membership.append({'id':r['id'],'native_shell_to_original_unit':native_to_source,'runtime_mesh_nodes':mesh_map,'note':'Derived runtime nodes may combine/reconstruct geometry; source_unit_id identifies provenance, not geometric equality. Missing source units have no surviving runtime node.'})
    bundles={}
    for name,predicate in [('rune-reference',lambda r:r['id'].startswith('rune/')),('outpost-armor-reference',lambda r:r['id'].startswith('outpost/')),('base-armor-reference',lambda r:r['id'].startswith('base/armor/'))]:
        composer=RigidComposer();composer.document['nodes'].append({'name':name});composer.document['scenes'][0]['nodes']=[0];total=0
        for r in filter(predicate,ledger['references']):
            d,b=read_glb(ROOT/r['reference_glb']);composer.append_definition(r['id'],d,b);composer.instantiate(r['id'],0);total+=r['triangles']
        dest=OUT/(name+'.glb');write_glb(dest,composer.document,composer.binary)
        bundles[name]={'path':str(dest.relative_to(ROOT)),'sha256':digest(dest),'triangles':total,'frame':'Original product axes, metres; identity component assembly, not full arena placement.'}
    transforms={}
    for label,relative in [('arena','manifest.json'),('equipment','equipment/manifest.json')]:
        path=ROOT.parent/'rm-simulator/field-2027'/relative;doc=json.loads(path.read_bytes())
        transforms[label]={'file':str(path.relative_to(ROOT.parent)),'sha256':digest(path),'floor_top_source_z_m':doc.get('floor_top_source_z_m'),'assets':{k:v for k,v in doc['assets'].items() if k in ['rune','outpost','tech-core','base']}}
    evidence={'bundles':bundles,'validation':verified,'source_runtime_membership':membership,'runtime_asset_placements':transforms,'producer_sha256':{p.name:digest(p) for p in BENCH.glob('*.py')},'placement_note':'Use source_world_occurrences for source arena placement. Runtime manifest placements are already in source arena metres, and the simulator applies its own arena-origin shift. Do not combine a full source occurrence with an asset placement. Rune motion parents cancel to identity in this rest pose.'}
    dump(OUT/'evidence.json',evidence);dump(BENCH/'evidence.json',evidence)
    print('Validated',len(verified),'references; bundled',bundles)

if __name__=='__main__':main()
