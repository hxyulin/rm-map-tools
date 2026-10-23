#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independently check private STEP appearance records against original source."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from p21index import Index
from cad_hierarchy import remap_record
from plan_cad_lods import digest
OUT=ROOT/'out/rmuc2027-protected-source-reference'
STYLE_TYPES={'STYLED_ITEM','OVER_RIDING_STYLED_ITEM','PRESENTATION_STYLE_ASSIGNMENT','SURFACE_STYLE_USAGE','SURFACE_SIDE_STYLE','SURFACE_STYLE_FILL_AREA','FILL_AREA_STYLE','FILL_AREA_STYLE_COLOUR','COLOUR_RGB','SURFACE_STYLE_RENDERING','SURFACE_STYLE_RENDERING_WITH_PROPERTIES','SURFACE_STYLE_TRANSPARENT','SURFACE_STYLE_REFLECTANCE_AMBIENT','SURFACE_STYLE_REFLECTANCE_AMBIENT_DIFFUSE','DRAUGHTING_PRE_DEFINED_COLOUR'}

def main():
    ledger=json.loads((OUT/'ledger.json').read_bytes());h=json.loads((ROOT/'out/rmuc2027-hierarchy/hierarchy.json').read_bytes());cs={c['id']:c for c in h['components']};results=[]
    with Index.from_step(ROOT/ledger['source_file'],workers=1,intern_layers=True) as full:
        for cid in dict.fromkeys(r['component_id'] for r in ledger['references']):
            c=cs[cid];mapping={sid:c['first_private_entity_id']+i for i,sid in enumerate(c['private_source_entity_ids'])};checked=0;counts={}
            with Index.from_step(ROOT/'out/rmuc2027-equipment-pipeline'/cid/'source.step',workers=1,intern_layers=True) as split:
                for sid,eid in mapping.items():
                    row=full.r(sid);kind=full.tname(row)
                    if kind not in STYLE_TYPES:continue
                    sr=split.r(eid)
                    if sr<0:continue # private namespace may include unused source style records
                    assert split.text(sr)==remap_record(full.text(row),mapping),(cid,sid,eid,kind)
                    counts[kind]=counts.get(kind,0)+1;checked+=1
            assert checked>0
            results.append({'id':cid,'private_appearance_records_exact_under_documented_id_remap':checked,'counts_by_type':counts})
            print(cid,checked,flush=True)
    result={'full_source_sha256':ledger['source_sha256'],'scope':'Private source appearance records used by each split checked byte-for-byte after the hierarchy namespace remap. Shared original records are checked by build.py. Unresolved OCCT diffuse values remain explicitly unresolved, not certified complete visual materials.','checks':results}
    for path in [OUT/'style-verification.json',Path(__file__).with_name('style-verification.json')]:path.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
