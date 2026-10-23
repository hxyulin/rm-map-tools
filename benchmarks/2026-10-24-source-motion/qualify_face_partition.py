"""Resolve reviewed carrier triangle ownership against exact original STEP faces."""
from pathlib import Path
import sys,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'python'))
from cad_document import CadDocument
from validate_parts import read_part
from cad_wall_fill import shape_map
from OCP.TopAbs import TopAbs_FACE
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
from OCP.collections import Sequence_TDF_Label
from OCP.STEPConstruct import STEPConstruct
from mesh_parts import tessellate
OUT=ROOT/'out/rmuc2027-source-motion';folder=ROOT/'out/rmuc2027-equipment-pipeline/outpost/fixed/upper-cluster';h=json.load(open(ROOT/'out/rmuc2027-hierarchy/hierarchy.json'));c=next(c for c in h['components']if c['id']=='outpost/fixed/upper-cluster')
z=np.load(folder/'native.npz');mask=np.zeros(len(z['triangles']),bool);mask[np.load(OUT/'outpost-carrier-triangle-selection.npz')['selected_triangle_indices']]=True
with CadDocument.from_step(folder/'source.step',workers=1) as cad:
 doc,reader,error=read_part(str(folder/'source.step'));assert not error,error
 labels=Sequence_TDF_Label();XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetFreeShapes(labels);shape=XCAFDoc_ShapeTool.GetShape_s(labels.Value(1));faces=shape_map(shape,TopAbs_FACE)
 model=reader.Reader().StepModel();process=reader.Reader().WS().MapReader();by_native={}
 for f in c['face_ids']:
  entity=model.Value(cad.index.r(f)+1);ni=faces.FindIndex(STEPConstruct.FindShape_s(process,entity));assert ni and ni not in by_native;by_native[ni]=f
 counts=[];stats={}
 p,t,m,palette=tessellate(doc,.4,.25,stats,lambda i,f,n:counts.append((by_native[i],n)))
 assert np.array_equal(p,z['positions_mm']) and np.array_equal(t,z['triangles'])
 fids=np.repeat([x[0]for x in counts],[x[1]for x in counts]);assert len(fids)==len(mask)
 selected=[];mixed=[]
 for f in np.unique(fids):
  take=mask[fids==f]
  if take.all():selected.append(int(f))
  elif take.any():mixed.append({'source_face_id':int(f),'moving_triangles':int(take.sum()),'total_triangles':len(take)})
 result={'source_face_ids':selected,'mixed_faces':mixed,'exact_mesh_equals_native':True,'faces':len(counts),'selected_triangles':int(mask.sum())}
 np.savez_compressed(OUT/'outpost-carrier-source-faces.npz',source_face_ids=fids,selected_mask=mask)
 (OUT/'outpost-carrier-source-faces.json').write_text(json.dumps(result,indent=2)+'\n');print('whole moving faces',len(selected),'mixed faces',len(mixed));print(mixed)
