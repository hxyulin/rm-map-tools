"""Stage a read-only local viewer of pinned unsimplified reference meshes."""
from pathlib import Path
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2];BENCH=Path(__file__).parent;OUT=ROOT/'out/rmuc2027-source-motion/review';OUT.mkdir(exist_ok=True)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
refs=json.loads((ROOT/'out/rmuc2027-protected-source-reference/ledger.json').read_text())['references'];inventory=json.loads((ROOT/'out/rmuc2027-equipment-pipeline/inventory.json').read_text())['components'];pins={}
def link(name,path,pin):
 assert sha(path)==pin,str(path)
 dst=OUT/name
 if dst.is_symlink():dst.unlink()
 assert not dst.exists(),dst
 dst.symlink_to(path);pins[name]={'path':str(path),'sha256':pin}
for name,cid in [('base.glb','base/source-model')]:
 r=next(r for r in refs if r['id']==cid);link(name,ROOT/r['reference_glb'],r['reference_glb_sha256'])
for name,cid in [('rune.glb',None)]:
 # Composite uses the individually verified source-unit GLBs; composite identity
 # is pinned here as well, while full source provenance remains in the ledger.
 path=ROOT/'out/rmuc2027-protected-source-reference/rune-reference.glb';link(name,path,sha(path))
files={}
for asset in ['outpost','dart-station']:
 files[asset]=[]
 for r in inventory:
  cid=r['id']
  if not cid.startswith(asset+'/'):continue
  name=cid.replace('/','--')+'.glb'
  if cid=='outpost/fixed/upper-cluster' and (OUT.parent/'layer-review.json').exists():
   review=json.loads((OUT.parent/'layer-review.json').read_text())['outpost'];link(name,Path(review['output']),review['output_sha256'])
  else:link(name,ROOT/'out/rmuc2027-equipment-pipeline'/cid/'native.glb',r['native_glb_sha256'])
  files[asset].append({'url':name+'?v='+pins[name]['sha256'][:16],'component':cid})
layers=json.loads((OUT.parent/'layer-review.json').read_text()) if (OUT.parent/'layer-review.json').exists() else {}
config={'layer_review':layers,'files':files,'motions':json.loads((OUT.parent/'motions.json').read_text()),'source_meshes':'unsimplified native .4mm / .25rad, no mesh reduction','pins':pins}
(OUT/'config.json').write_text(json.dumps(config,indent=2)+'\n')
for name in ['index.html','viewer.js']:shutil.copyfile(BENCH/name,OUT/name)
html=OUT/'index.html';html.write_text(html.read_text().replace('src="viewer.js"','src="viewer.js?v='+sha(OUT/'viewer.js')[:16]+'"'))
print('Staged',len(pins),'pinned source-reference files',OUT)
