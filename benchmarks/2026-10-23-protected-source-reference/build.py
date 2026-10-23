#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build unsimplified protected references from existing analytic STEP splits.

Run from any directory with rm-map-tools/ocpenv/bin/python. Only OUTPUT and
this benchmark's generated ledger are written. No installed mesh is an input
for reference geometry. Runtime GLBs are read solely for mapping/comparison.
"""
import collections
import gc
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'python'))
from cad_document import CadDocument
from p21index import Index
from cad_wall_fill import shape_map
from mesh_parts import tessellate
from validate_parts import read_part
from export_field_package import GlbWriter
from gltf_scene import read_glb, scene_nodes, accessor
from plan_cad_lods import build_plan, digest
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.STEPConstruct import STEPConstruct
OUTPUT = ROOT/'out/rmuc2027-protected-source-reference'
BENCH = Path(__file__).resolve().parent
SHA = 'a5ad3ede3b7674fc98f2e73b71717216383cb2b4b5dcdbe900c2038918bea8e0'
BASE_IDS = [4099408,4121375,4143351,4314593,4353403,4392221]


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def runtime_file(cid):
    return ROOT.parent/'rm-simulator/field-2027'/({'technology-core':'equipment/tech-core.glb','base':'equipment/base.glb','outpost':'outpost.glb','rune':'rune.glb'}[cid.split('/')[0]])


def runtime_mapping(cid, body=None):
    path=runtime_file(cid);d,b=read_glb(path);frames={i:w for i,w,p in scene_nodes(d)}
    component=next(i for i,n in enumerate(d['nodes']) if n.get('extras',{}).get('component_id')==cid)
    def descendants(i):
        yield i
        for child in d['nodes'][i].get('children',[]):yield from descendants(child)
    selected=list(descendants(component))
    if body is not None:
        selected=[i for i in selected if d['nodes'][i].get('name') in (f'source_body_{body}',f'base/source-model/solid-{body}') or d['nodes'][i].get('extras',{}).get('source_unit_id')==body]
        # Production Base exporter uses native unit labels, inspected explicitly below.
        if not selected:
            selected=[i for i,n in enumerate(d['nodes']) if str(body) in n.get('name','') and 'mesh' in n]
        if not selected:raise ValueError(f'No runtime body mapping for {body}')
    mesh_nodes=[i for i in selected if 'mesh' in d['nodes'][i]]
    tris=sum((d['accessors'][p['indices']]['count']//3 if 'indices' in p else d['accessors'][p['attributes']['POSITION']]['count']//3) for i in mesh_nodes for p in d['meshes'][d['nodes'][i]['mesh']]['primitives'])
    return {'file':str(path.relative_to(ROOT.parent)), 'sha256':digest(path), 'component_root_node_index':component,'component_root_node':d['nodes'][component], 'component_rest_matrix_m':frames[component].tolist(),'mesh_nodes':[{'index':i,'name':d['nodes'][i].get('name'),'rest_matrix_m':frames[i].tolist(),'extras':d['nodes'][i].get('extras',{})} for i in mesh_nodes], 'triangles':tris}


def main():
    OUTPUT.mkdir(exist_ok=True,parents=True)
    source=ROOT/'source/RMUC2027_V1.0.0.stp';hp=ROOT/'out/rmuc2027-hierarchy/hierarchy.json';h=json.loads(hp.read_bytes())
    assert digest(source)==SHA==h['source_sha256']
    assert digest(hp.with_name('field.step'))==h['files_sha256']['field.step']
    plan=build_plan(h)
    components=[c for c in h['components'] if c['id']=='technology-core/tool-head' or c['id'].startswith(('rune/','outpost/rotor/')) or c['id']=='base/source-model']
    rows=[];checks=[]
    if '--only-base' in sys.argv:
        previous=json.loads((OUTPUT/'ledger.json').read_bytes())
        rows=[r for r in previous['references'] if r['component_id']!='base/source-model']
        checks=[r for r in previous['checks'] if r['id']!='base/source-model']
        components=[c for c in components if c['id']=='base/source-model']
    # Parsing only, never load the full arena into OCCT.
    with Index.from_step(source,workers=1,intern_layers=True) as full:
        fullfaces=set(map(int,full.ids[full.rows_of('ADVANCED_FACE')]))
        assert fullfaces=={f for c in h['components'] for f in c['face_ids']}
        for c in components:
            cid=c['id'];folder=ROOT/'out/rmuc2027-equipment-pipeline'/cid
            pin=json.loads((folder/'native.json').read_bytes())
            assert digest(folder/'source.step')==pin['source_step_sha256']
            assert digest(hp)==pin['hierarchy_sha256']
            print('Building',cid,flush=True)
            with CadDocument.from_step(folder/'source.step',workers=1,intern_layers=True) as cad:
                ix=cad.index
                # Original geometry IDs/bytes retained by the hierarchical split.
                shared=0;shared_hash=hashlib.sha256()
                for r in range(ix.n):
                    sid=int(ix.ids[r]);fr=full.r(sid)
                    if fr>=0:
                        assert ix.text(r)==full.text(fr),(cid,sid)
                        shared_hash.update(ix.text(r)+b'\n');shared+=1
                doc,reader,error=read_part(str(folder/'source.step'));assert not error,error
                labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels);assert labels.Length()==1
                shape=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));faces=shape_map(shape,TopAbs_FACE)
                model=reader.Reader().StepModel();process=reader.Reader().WS().MapReader();assert model.NbEntities()==ix.n
                by_native={}
                for f in c['face_ids']:
                    entity=model.Value(ix.r(f)+1);assert entity.DynamicType().Name()=='StepShape_AdvancedFace'
                    ni=faces.FindIndex(STEPConstruct.FindShape_s(process,entity));assert ni and ni not in by_native
                    by_native[ni]=f
                assert len(by_native)==faces.Extent()==c['face_count']
                owners={};owner_kinds={}
                for body in c['solid_body_ids']:
                    owner_kinds[body]='solid'
                    for r in cad.model.body_faces(ix.r(c['export_body_ids'][str(body)])):
                        f=int(ix.ids[r]);assert f not in owners;owners[f]=body
                for body,shells in c['shell_ids_by_body'].items():
                    for shell in shells:
                        owner_kinds[shell]='surface-shell'
                        for f in ix.refs_of(ix.r(shell)):
                            f=int(f);assert f not in owners;owners[f]=shell
                assert set(owners)==set(c['face_ids'])
                records=[];stats={}
                def observe(i,face,n):records.append((by_native[i],owners[by_native[i]],n))
                p,t,m,palette=tessellate(doc,.4,.25,stats,observe)
                assert not stats.get('unmeshed_faces') and len(records)==len(by_native)
                fids=np.repeat([r[0] for r in records],[r[2] for r in records]);units=np.repeat([r[1] for r in records],[r[2] for r in records]);assert len(fids)==len(t)
                cache_equal=None
                if (folder/'native.npz').exists():
                    assert digest(folder/'native.npz')==pin['native_npz_sha256']
                    cached=np.load(folder/'native.npz')
                    cache_equal=all(np.array_equal(a,cached[k]) for a,k in [(p,'positions_mm'),(t,'triangles'),(m,'material_ids')]) and [v or '' for v in palette]==cached['palette'].tolist()
                    assert cache_equal,'native cache differs from fresh tessellation'
                assert len(t)==pin['native_triangles']
                selections=[(cid,None)] if cid!='base/source-model' else [(cid,None)]+[(f'base/armor/body-{body}',body) for body in BASE_IDS]
                for label,body in selections:
                    select=np.ones(len(t),bool) if body is None else units==body
                    tt=t[select];mm=m[select];uu=units[select];ff=fids[select]
                    assert len(tt)>0
                    dest=OUTPUT/label;dest.mkdir(parents=True,exist_ok=True)
                    writer=GlbWriter(label,{'version':'2.0','copyright':'DJI / RoboMaster original geometry and appearance','extras':{'source_sha256':SHA,'source_product_id':c['source_product_id'],'unsimplified':True,'linear_deflection_mm':.4,'angular_deflection_rad':.25}})
                    for unit in np.unique(uu):
                        ids=np.flatnonzero(uu==unit);used,inv=np.unique(tt[ids],return_inverse=True)
                        writer.add_node(f'{label}/{owner_kinds[int(unit)]}-{unit}',p[used]/1000,inv.reshape(-1,3),[palette[int(k)] for k in mm[ids]],extras={'source_unit_id':int(unit),'source_unit_kind':owner_kinds[int(unit)]})
                    writer.write(dest/'reference.glb')
                    np.savez_compressed(dest/'reference.npz',positions_mm=p,triangles=tt,material_ids=mm,palette=np.array([v or '' for v in palette]),source_face_ids=ff,source_unit_ids=uu)
                    mapping=runtime_mapping(cid,body)
                    record={'id':label,'component_id':cid,'source_product_id':c['source_product_id'],'export_product_id':c['export_product_id'],'source_body_ids':c['solid_body_ids'] if body is None else [body],'source_shell_ids_by_body':c['shell_ids_by_body'] if body is None else {},'source_face_ids':sorted(set(map(int,ff))),'source_units':{str(u):owner_kinds[int(u)] for u in np.unique(uu)},'source_step':str((folder/'source.step').relative_to(ROOT)),'source_step_sha256':pin['source_step_sha256'],'triangles':len(tt),'palette':palette,'triangles_by_source_color':dict(collections.Counter(str(palette[int(k)]) for k in mm)),'unresolved_source_color_triangles':sum(palette[int(k)] is None for k in mm),'fresh_tessellation_equals_native_cache':cache_equal,'reference_glb':str((dest/'reference.glb').relative_to(ROOT)),'reference_glb_sha256':digest(dest/'reference.glb'),'reference_npz_sha256':digest(dest/'reference.npz'),'runtime':mapping,'source_world_occurrences':[n for n in plan['nodes'] if n['component_id']==cid]}
                    dump(dest/'mapping.json',record);rows.append(record)
                checks.append({'id':cid,'source_faces':faces.Extent(),'source_units':len(owner_kinds),'native_triangles':len(t),'stats':stats,'shared_original_records_byte_equal':shared,'shared_records_sha256':shared_hash.hexdigest(),'source_native_face_bijection':True,'native_json_sha256':digest(folder/'native.json')})
            del doc,reader,p,t,m;gc.collect()
    report={'source_file':str(source.relative_to(ROOT)),'source_sha256':SHA,'source_bytes':source.stat().st_size,'hierarchy_sha256':digest(hp),'hierarchical_step_sha256':h['files_sha256']['field.step'],'full_source_faces_verified':len(fullfaces),'hierarchy_source_coverage':{k:h[k] for k in ['source_body_definitions','source_placed_bodies','source_product_occurrences','source_face_definitions','expected_placed_faces','geometry_record_sha256','original_geometry_records']},'tessellation':{'linear_deflection_mm':.4,'angular_deflection_rad':.25,'simplification':False},'coordinate_contract':'Reference GLBs: original product-local coordinates / 1000, metres, original source axes. NPZ positions are mm. source_world_occurrences.world_matrix_mm transforms original local mm into full source arena mm. Runtime component_rest_matrix_m is the CURRENT rest node transform within asset, not the full arena placement. These components are baked in product local coordinates; apply asset placement once.','checks':checks,'references':rows}
    dump(OUTPUT/'ledger.json',report);dump(BENCH/'ledger.json',report)
    print('Completed',len(rows),'protected references',flush=True)

if __name__=='__main__':main()
