import json,numpy as np
parts=json.load(open('../rm-map-tools/out/rm2027/RMUC2027_V1.0.0/split/parts.json'))['parts']
for product in [2603236,1354629]:
 p=next(p for p in parts if p['product_id']==product);bodies=p['bodies'];by={b['id']:b for b in bodies}
 sets=[]
 if product==2603236:
  sets=[('lower',[1842355,1843213,1844071,2433633]),('column',[1920483,1925186,1929889]),('upper',[b['id'] for b in bodies if b['id']>=2408935 and b['id']<=2432388]+[2101579])]
 else:
  arm=[b['id'] for b in bodies if 232961<=b['id']<=694691]
  for i in range(10):sets.append((f'arm-{i}',arm[i*10:i*10+10]))
  sets += [('hub-a',[b['id'] for b in bodies if 69537<=b['id']<=146846]),('hub-b',[b['id'] for b in bodies if 147664<=b['id']<=224972])]
 for name,ids in sets:
  lo=np.min([by[b]['bbox_min'] for b in ids],axis=0)-1;hi=np.max([by[b]['bbox_max'] for b in ids],axis=0)+1
  contained=[b['id'] for b in bodies if np.all(np.array(b['bbox_min'])>=lo) and np.all(np.array(b['bbox_max'])<=hi)]
  cross=[b['id'] for b in bodies if b['id'] not in contained and np.all(np.array(b['bbox_max'])>=lo) and np.all(np.array(b['bbox_min'])<=hi)]
  print(product,name,'expected',len(ids),'contained',len(contained),'extra',sorted(set(contained)-set(ids)),'crossing',cross)
