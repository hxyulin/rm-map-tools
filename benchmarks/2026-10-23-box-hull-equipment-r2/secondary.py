from research import *
def run():
 ref=json.loads(REF.read_text());rows=[]
 for asset in ['tech-core','base','outpost']:
  doc,comp,nodes=load_nodes(Path(ref['roles']['collision']['assets'][asset]['path']))
  for ni,g in nodes.items():
   if asset=='tech-core' and (ni in [22,68] or comp[ni]=='technology-core/tool-head'):continue
   _,_,labels,n=topology(g)
   for label in range(n):
    h=g[labels==label]
    if len(h)<80 or len(h)>=160 or np.ptp(h.reshape(-1,3),axis=0).max()<40:continue
    p=np.unique(h.reshape(-1,3),axis=0)
    try:hu=ConvexHull(p)
    except QhullError:continue
    target=p[hu.simplices]
    if len(target)>len(h)//2:continue
    fv=dist(p,target);fs=dist(area_samples(h,8000,31),target);rs=dist(area_samples(target,8000,37),h)
    mm=max(fv.max(),fs.max(),rs.max())
    print(asset,ni,label,len(h),len(target),mm,comp[ni],flush=True)
    rows.append(dict(asset=asset,node=ni,island=label,source_triangles=len(h),hull_triangles=len(target),source_all_vertex_max_mm=float(fv.max()),source_area_max_mm=float(fs.max()),reverse_area_max_mm=float(rs.max()),**selector(np.flatnonzero(labels==label))))
 (OUT/'secondary.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':run()
