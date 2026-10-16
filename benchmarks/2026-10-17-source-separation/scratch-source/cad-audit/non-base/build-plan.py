import json,numpy as np
from pathlib import Path
parts=json.load(open('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/split/parts.json'))['parts']
source=json.load(open('../rm-map-tools/rules/components-rmuc2027.json'))['source_sha256']
plan={'_license':'SPDX-License-Identifier: MIT OR Apache-2.0','_copyright':'Copyright (c) 2026 hxyulin <hxyulin@proton.me> (selection policy; source CAD identities retain upstream ownership)','schema_version':1,'source_sha256':source,'coordinate_frame':'product-local','length_unit':'millimetre','regions':[]}
for product in [2603236,1354629]:
 bodies=next(p['bodies'] for p in parts if p['product_id']==product);by={b['id']:b for b in bodies}
 if product==2603236:
  sets=[('outpost/fixed/lower-cluster',[1842355,1843213,1844071,2433633]),('outpost/fixed/column-cluster',[1920483,1925186,1929889]),('outpost/fixed/upper-cluster',[b['id'] for b in bodies if 2408935<=b['id']<=2432388]+[2101579])]
 else:
  arm=[b['id'] for b in bodies if 232961<=b['id']<=694691]
  sets=[(f'rune/banks/bank-{chr(97+i//5)}/arm-{i%5}',arm[i*10:i*10+10]) for i in range(10)]
  sets += [('rune/banks/bank-a/hub-cluster',[b['id'] for b in bodies if 147664<=b['id']<=224972]),('rune/banks/bank-b/hub-cluster',[b['id'] for b in bodies if 69537<=b['id']<=146846]+[228756])]
 for name,ids in sets:
  lo=np.min([by[b]['bbox_min'] for b in ids],axis=0)-1;hi=np.max([by[b]['bbox_max'] for b in ids],axis=0)+1
  evidence=['Manual whole-body candidate from repeated source body face-count patterns and product-local vertex bounds. Region uses their union plus 1 mm. No mechanical role or motion is certified.']
  if product==1354629 and '/arm-' in name:evidence.append('Ten-body candidate signature: 105,101,157,121,121,157,190,34,40,40 source faces; repeated in ten spatial clusters.')
  r={'id':name,'product_id':product,'min_mm':lo.tolist(),'max_mm':hi.tolist(),'expected_body_ids':ids,'evidence':evidence}
  if product==2603236:r['motion_filter']={'motion':'fixed','motion_owner':'outpost.frame'};r['evidence'].append('Filter uses existing reviewed outpost.frame binding; the upper box also contains the separately retained moving rotor modules.')
  plan['regions'].append(r)
Path('../rm-map-tools/rules/component-regions-rmuc2027.json').write_text(json.dumps(plan,indent=2)+'\n')
