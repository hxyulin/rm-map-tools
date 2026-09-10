import sys, os, collections, time, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from p21index import Index; from p21model import Model; from p21split import Splitter
import numpy as np
npz, out = sys.argv[1], sys.argv[2]
ix=Index(npz); m=Model(ix); sp=Splitter(ix,m)
count=np.zeros(ix.n, np.int32); t=time.time()
prods=[p for p in m.product_name if p in m.product_reps]
for p in prods:
    mask,_=sp.closure(p); count[mask]+=1
never=collections.Counter(ix.tname(r) for r in np.nonzero(count==0)[0])
multi=collections.Counter(ix.tname(r) for r in np.nonzero(count>1)[0])
res=dict(entities=ix.n, products=len(prods), in_no_part=int((count==0).sum()), in_one_part=int((count==1).sum()), in_many_parts=int((count>1).sum()),
         never_types=dict(never.most_common()), multi_types=dict(multi.most_common(25)), seconds=round(time.time()-t,1))
json.dump(res, open(out,'w'), indent=1); print(json.dumps(res)[:1500])
