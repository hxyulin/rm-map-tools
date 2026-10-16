# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Author explicit source-shell work boundaries from the reviewed discovery report."""
import json
from pathlib import Path
import numpy as np
r=json.load(open('local-assets/cad-audit/non-base/regions-with-shells.json'))
by={s['shell_id']:s for s in r['source_shells']}
policy={'_license':'SPDX-License-Identifier: MIT OR Apache-2.0','_copyright':'Copyright (c) 2026 hxyulin <hxyulin@proton.me> (partition policy; source CAD identities retain upstream ownership)',
 'schema_version':1,'source_sha256':r['source_sha256'],'length_unit':'millimetre','notes':[
 'Partition original solid bodies and complete source shells; do not crop faces or modify native geometry.',
 'Work grouping proposes attachment only; it does not change runtime motion, lights, collision or scoring.',
 'Rune arm boxes include a nearby 453-face cover shell. Prefer specific arm boxes over broad hub boxes. One-face shell matches remain outside arm groups to preserve the repeated 95-shell/999-face surface pattern.',
 'All unmatched/conflicting source shells remain explicitly exported in a support-and-shared group.'], 'products':[]}
for pid,name,parent in [(2603236,'outpost',2601775),(1354629,'rune',1354072)]:
 spec={'product_id':pid,'name':name,'fallback_group':name+'/support-and-shared','body_group_overrides':{name+'/other-bodies':name+'/support-and-shared'},'shell_rules':[]}
 if name=='outpost':
  assignments=[('rotor/module-0',[2498962]),('rotor/module-1',[2527556]),('rotor/module-2',[2556150]),('fixed/lower-cluster',[2439250,2443527,2447822,2454924,2462026,2470368]),('fixed/upper-cluster',[2560247,2564056,2568239,2571808,2601768])]
  for group,ids in assignments:
   spec['shell_rules'].append({'id':name+'/'+group,'body_id':parent,'group':name+'/'+group,'priority':1000,'shell_ids':ids,'evidence':['Manual original-shell grouping from source bounds: three separate 688-face module surrounds, six lower-region shells and five upper-region shells. Attachment/motion remains a work proposal.']})
 else:
  arms=[q for q in r['regions'] if q['product_id']==pid and '/arm-' in q['id']]
  covers=[907068,953700,1000332,1046964,1093596,1141790,1188422,1235054,1281686,1328318]
  for q,cover in zip(arms,covers):
   lo=np.minimum(q['min_mm'],np.array(by[cover]['min_mm'])-1);hi=np.maximum(q['max_mm'],np.array(by[cover]['max_mm'])+1)
   spec['shell_rules'].append({'id':q['id'],'body_id':parent,'group':q['id'],'priority':100,'min_mm':lo.tolist(),'max_mm':hi.tolist(),'exclude_face_counts':[1], 'evidence':[f'Manual union of mechanical arm region and original 453-face shell #{cover}, padded 1 mm. This cover requires 20–48 mm expansion, versus at least ~480 mm to the next arm box.', 'All ten arms reproduce 95 whole surface shells with 999 source faces; one-face incidental matches remain outside arm groups. Specific arm ownership precedes overlapping hub regions.']})
  for q in r['regions']:
   if q['product_id']==pid and '/hub-' in q['id']:
    spec['shell_rules'].append({'id':q['id'],'body_id':parent,'group':q['id'],'priority':50,'min_mm':q['min_mm'],'max_mm':q['max_mm'],'evidence':['Existing source hub-region bounds, lower priority than contained arm selections; no center-based shell assignment.']})
  spec['expected_group_signatures']={q['id']:[10,95,2065] for q in arms}
 policy['products'].append(spec)
Path('../rm-map-tools/rules/partition-rmuc2027.json').write_text(json.dumps(policy,indent=2)+'\n')
