import sys,json,hashlib
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path('../rm-map-tools/python').resolve()))
from cad_document import CadDocument
from p21model import STR_RE,decode_p21

def main():
 with CadDocument.from_index('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/source.npz') as doc:
  ix=doc.index;groups=defaultdict(list);types=Counter();records=[]
  for row in ix.rows_of('PRESENTATION_LAYER_ASSIGNMENT'):
   raw=ix.text(int(row));strings=STR_RE.findall(raw)
   name,desc=[decode_p21(v) for v in strings[:2]]
   refs=ix.refs_of(int(row));inrange=refs<=ix.max_id;rows=ix.row[refs[inrange]];valid=rows>=0
   counts={ix.typenames[int(t)]:int(n) for t,n in zip(*np.unique(ix.types[rows[valid]],return_counts=True))}
   types.update(counts)
   rec={'id':int(ix.ids[row]),'name':name,'description':desc,'targets':len(refs),'target_types':counts,'membership_sha256':hashlib.sha256(refs.tobytes()).hexdigest()}
   records.append(rec);groups[name].append(rec)
  result={'source_sha256':doc.source_sha256,'layers':len(records),'unique_names':len(groups),'target_references':sum(r['targets'] for r in records),'target_types':dict(types),'names':[{'name':name,'declarations':len(rs),'references':sum(r['targets'] for r in rs),'descriptions':sorted({r['description'] for r in rs}),'examples':rs[:2]} for name,rs in sorted(groups.items(),key=lambda item:-sum(r['targets'] for r in item[1]))]}
  Path('local-assets/cad-audit/layers-probe.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
  print(json.dumps({k:v for k,v in result.items() if k!='names'},indent=2));print(json.dumps(result['names'][:24],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
