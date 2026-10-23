# SPDX-License-Identifier: MIT OR Apache-2.0
"""Record the topology-qualified alternatives without copying baseline files."""
import copy,json
from pathlib import Path
import trial

def main():
 path=trial.OUT/'coarse/ledger.json';r=json.loads(path.read_text());verification=json.loads((path.parent/'verification.json').read_text())
 r['topology_review_required']={'arena-static/visual':'Open material group: boundary edges 4323 -> 4610; nonmanifold edges 245 -> 227 per Dart placement under 0.00001mm position weld. Local capped aperture domains are checked; assembly closure is not certified. Keep baseline Dart in the prism-only alternative.'}
 prism=copy.deepcopy(r['stage_inputs'])
 for row in prism:
  if row['asset']=='arena-static':row['candidate']=row['baseline'];row['candidate_sha256']=row['baseline_sha256']
 r['alternatives']={'coarse_prisms_only':{'stage_inputs':prism,'placed_visual_triangles':198121,'placed_collision_triangles':196332,'placed_visual_saving':898},'coarse_with_dart_apertures':{'stage_inputs':r['stage_inputs'],'placed_visual_triangles':197893,'placed_collision_triangles':196332,'placed_visual_saving':1126,'requires_Dart_topology_review':True}}
 r['optical_review_caveat']='Base artwork backing 4268930 excluded completely. No assembled changed/protected triangle intersections detected, but finite checks do not certify rendered artwork masks; parent owns seven-view gallery.'
 r['producer_sha256']={str(p.resolve()):trial.digest(p) for p in Path(__file__).parent.glob('*.py')}
 path.write_text(json.dumps(r,indent=2)+'\n')
 compact={'candidate_ledger':str(path.resolve()),'assets':{k:{f:v[f] for f in ['output','output_sha256','baseline','baseline_sha256','input','input_sha256','baseline_stored_triangles','candidate_stored_triangles','baseline_placed_triangles','candidate_placed_triangles']} for k,v in r['assets'].items()},'totals':verification['placed_totals'],'prisms_only_visual_total':198121,'near_result':'No cheaper replacement retained at 1.2mm sampled allowance.','scope':'Inspection only. Dart topology warning is explicit in full ledger. No runtime timing or installation.'}
 (Path(__file__).parent/'results.json').write_text(json.dumps(compact,indent=2)+'\n')
if __name__=='__main__':main()
