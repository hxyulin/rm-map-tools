import sys,json,collections,numpy as np
sys.path.insert(0,'../rm-map-tools/python')
from cad_document import CadDocument
from audit_component_regions import classify_box
plan=json.load(open('../rm-map-tools/rules/component-regions-rmuc2027.json'))
with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as d:
 for product,bid in [(2603236,2601775),(1354629,1354072)]:
  shells=[]
  for sid in d.entity(bid).reference_ids:
   row=d.index.r(int(sid));lo,hi,n=d.model.body_bbox(row);shells.append((int(sid),lo,hi,len(d.model.body_faces(row))))
  print('source',product,'shells',len(shells),'faces',sum(s[3] for s in shells))
  for r in plan['regions']:
   if r['product_id']!=product:continue
   found=collections.defaultdict(list)
   for sid,lo,hi,n in shells:
    if lo is not None:found[classify_box(lo,hi,np.array(r['min_mm']),np.array(r['max_mm']))].append((sid,n))
   print(r['id'],'contained',len(found['contained']),sum(n for s,n in found['contained']),'straddling',len(found['straddling']))
