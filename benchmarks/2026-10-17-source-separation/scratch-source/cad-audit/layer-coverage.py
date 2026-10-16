import sys,json,re,hashlib
from pathlib import Path
from collections import Counter
import numpy as np
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
from cad_document import CadDocument
from p21model import STR_RE,decode_p21

def main():
 with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as doc:
  ix=doc.index;hits=np.zeros(ix.n,np.int32);lists=Counter();names=[];color=[];descriptions=[];samples=[]
  for row in ix.rows_of('PRESENTATION_LAYER_ASSIGNMENT'):
   strings=STR_RE.findall(ix.text(int(row)));name,desc=[decode_p21(v) for v in strings[:2]]
   refs=ix.refs_of(int(row));rows=ix.row[refs];unique=np.unique(rows[rows>=0]);hits[unique]+=1
   lists[hashlib.sha256(np.sort(refs).tobytes()).hexdigest()]+=1
   names.append(name)
   if re.fullmatch(r'COLOR\d+(?:_\d+)*',name,re.I):color.append(name)
   if desc:descriptions.append(desc)
   if re.search(r'base|dart|armor|led|floor|paint|decor|light|static|body|ramp|基地|装甲|地面|涂',name,re.I):samples.append(name)
  covered={}
  for kind in ['ADVANCED_FACE','MANIFOLD_SOLID_BREP','BREP_WITH_VOIDS','SHELL_BASED_SURFACE_MODEL','B_SPLINE_CURVE_WITH_KNOTS','STYLED_ITEM']:
   ids=ix.rows_of(kind);h=hits[ids];covered[kind]={'source_count':len(ids),'covered':int((h>0).sum()),'multiple_layers':int((h>1).sum()),'maximum_layers':int(h.max()) if len(h) else 0,'median_layers_when_covered':float(np.median(h[h>0])) if (h>0).any() else 0}
  result={'source_sha256':doc.source_sha256,'color_named_layers':len(color),'other_named_layers':len(names)-len(color),'nonempty_descriptions':len(descriptions),'unique_membership_sets':len(lists),'repeated_membership_sets':sum(v>1 for v in lists.values()),'redundant_membership_sets':sum(v-1 for v in lists.values()),'coverage':covered,'keyword_name_matches':samples[:80]}
  Path('local-assets/cad-audit/layer-coverage.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n');print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
