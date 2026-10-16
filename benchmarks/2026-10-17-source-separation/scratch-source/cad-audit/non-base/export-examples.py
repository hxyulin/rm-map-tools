# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Export representative non-base work items from the verified component catalog."""
import json,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
from cad_document import CadDocument
from cad_components import select_components,export_selection
from validate_parts import read_part
from export_step_elements import shape_counts
catalog_path=Path('local-assets/cad-components/rmuc2027/catalog-non-base.json')
catalog=json.loads(catalog_path.read_text())
report=[]
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz',expected_sha256=catalog['source_sha256']) as doc:
 for selector,name in [('outpost/rotor/module-0','outpost-module-0-mechanical'),('outpost/fixed/lower-cluster','outpost-lower-cluster'),('rune/banks/bank-a/arm-0','rune-bank-a-arm-0-mechanical')]:
  selection=select_components(catalog,selector)
  selection['catalog_sha256']=hashlib.sha256(catalog_path.read_bytes()).hexdigest()
  selection['notes']=['Whole-body work selection; neighboring or overlapping surface-model shells are listed separately in the region audit and not included.']
  out=Path('local-assets/cad-components/rmuc2027/non-base')/name
  export_selection(doc,selection,out)
  native,reader,error=read_part(str(out/'source.step'))
  if error:raise RuntimeError(error)
  counts=list(shape_counts(native));expected=sum(c['source_faces'] for c in selection['components'])
  if counts[1]!=expected:raise ValueError('native import changed face count')
  entry={'selector':selector,'body_definitions':len(selection['components']),'placements':len(selection['occurrences']),'native_solids':counts[0],'native_faces':counts[1],'source_faces':expected,'work_directory':str(out)}
  report.append(entry);print(json.dumps(entry),flush=True)
  del native,reader
Path('local-assets/cad-audit/non-base/work-exports.json').write_text(json.dumps(report,indent=2)+'\n')
